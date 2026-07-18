"""Tavily-backed product label resolver.

Requires TAVILY_API_KEY in backend/.env or the process environment. The API key
is never logged. Results are cached in memory by normalized product query.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NotRequired, Protocol, TypedDict

from dotenv import load_dotenv

from services.source_policy import classify_product_source, hostname

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

NUTRITION_KEYS = {
    "serving_size",
    "calories",
    "total_sugar_g",
    "added_sugar_g",
    "fiber_g",
    "protein_g",
    "sodium_mg",
    "total_fat_g",
    "saturated_fat_g",
    "trans_fat_g",
    "cholesterol_mg",
    "total_carbohydrate_g",
    "vitamin_d_mcg",
    "calcium_mg",
    "iron_mg",
    "potassium_mg",
}


class ProductNutrition(TypedDict):
    serving_size: str | None
    calories: float | None
    total_sugar_g: float | None
    added_sugar_g: float | None
    fiber_g: float | None
    protein_g: float | None
    sodium_mg: float | None
    total_fat_g: float | None
    saturated_fat_g: float | None
    trans_fat_g: float | None
    cholesterol_mg: float | None
    total_carbohydrate_g: float | None
    vitamin_d_mcg: float | None
    calcium_mg: float | None
    iron_mg: float | None
    potassium_mg: float | None
    additional_nutrients: dict[str, float | str]


class ResolvedProduct(TypedDict):
    name: str
    brand: str | None
    ingredients: list[str]
    nutrition: ProductNutrition
    label_source_url: str
    label_source_type: Literal["manufacturer", "retailer", "food_database"]
    confidence: Literal["high", "medium"]


class ProductCandidate(TypedDict):
    name: str
    brand: str | None
    label_source_url: str
    reason: str


class DebugTrace(TypedDict):
    query: str
    result_count: int
    tavily_query_count: int
    selected_source_url: str | None
    decisions: list[dict[str, Any]]


class ProductResolution(TypedDict):
    status: Literal["resolved", "needs_confirmation", "not_found"]
    query: NotRequired[str]
    product: NotRequired[ResolvedProduct]
    candidates: NotRequired[list[ProductCandidate]]
    reason: NotRequired[str]
    debug: NotRequired[DebugTrace]


class TavilyConfigurationError(RuntimeError):
    """Raised when Tavily cannot be configured safely."""


class ProductResolutionError(RuntimeError):
    """Raised for user-safe Tavily product-resolution failures."""


class TavilyClientProtocol(Protocol):
    def search(self, **kwargs) -> dict:
        ...


@dataclass
class ProductResolverSettings:
    ttl_seconds: int = int(os.getenv("PRODUCT_RESOLVER_CACHE_TTL_SECONDS", "900"))
    max_results: int = int(os.getenv("TAVILY_PRODUCT_MAX_RESULTS", "5"))
    timeout_seconds: float = float(os.getenv("TAVILY_TIMEOUT_SECONDS", "12"))
    search_depth: str = os.getenv("TAVILY_SEARCH_DEPTH", "basic")


_CACHE: dict[str, tuple[float, ProductResolution]] = {}

LOW_QUALITY_PRODUCT_TERMS = {
    "blog",
    "recipe",
    "review",
    "coupon",
    "reddit",
    "pinterest",
    "youtube",
    "tiktok",
    "facebook",
}

VARIANT_TERMS = {
    "mini",
    "minis",
    "king",
    "fun size",
    "ice cream",
    "almond",
    "peanut butter",
    "protein",
    "zero sugar",
    "dark",
    "white",
    "bites",
}


def _normalize_query(product_name: str) -> str:
    return re.sub(r"\s+", " ", product_name.strip().lower())


def _get_client() -> TavilyClientProtocol:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise TavilyConfigurationError("TAVILY_API_KEY is missing. Add it to backend/.env.")

    from tavily import TavilyClient

    return TavilyClient(api_key=api_key)


def _text(result: dict) -> str:
    return " ".join(
        str(result.get(key, "")) for key in ("title", "content", "raw_content") if result.get(key)
    )


def _search_blob(result: dict) -> str:
    return f"{_title(result)} {_text(result)} {result.get('url') or ''}".lower()


def _title(result: dict) -> str:
    return str(result.get("title") or "").strip()


def _normalize_ingredient(item: str) -> str:
    cleaned = re.sub(r"\s+", " ", item).strip(" .;:()[]")
    cleaned = re.sub(r"^(and|or|contains|ingredients?)\s+", "", cleaned, flags=re.IGNORECASE)
    if "(" in cleaned and ")" not in cleaned:
        cleaned = cleaned.split("(", 1)[0].strip()
    return cleaned


def _extract_ingredients(text: str) -> list[str]:
    match = re.search(
        r"(?:ingredients?|ingredient list)\s*[:\-]\s*(.+?)(?:\n\s*\n|\.\s*(?:contains|allergen|nutrition|serving)| nutrition facts| may contain |$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []

    raw = re.sub(r"\s+and\s+", ", ", match.group(1), flags=re.IGNORECASE)
    raw = re.split(
        r"(?:[.;:]?\s*)\b(?:contains|may contain|contains less than|allergen information)\b",
        raw,
        flags=re.IGNORECASE,
    )[0]
    items = [_normalize_ingredient(item) for item in raw.split(",")]
    return [
        item
        for item in items
        if 2 < len(item) <= 80 and not re.search(r"\b(check|website|accurate|nutrition facts)\b", item, re.I)
    ][:40]


def _number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _normalize_nutrient_key(label: str, unit: str | None) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    unit_key = (unit or "").lower()
    if unit_key in {"g", "mg", "mcg"} and not key.endswith(f"_{unit_key}"):
        key = f"{key}_{unit_key}"
    if unit_key == "%":
        key = f"{key}_dv_percent"
    return key


def _extract_additional_nutrients(text: str, known_keys: set[str]) -> dict[str, float | str]:
    additional: dict[str, float | str] = {}
    known_labels = {
        "serving size",
        "calories",
        "total sugars",
        "added sugars",
        "dietary fiber",
        "fiber",
        "protein",
        "sodium",
        "total fat",
        "saturated fat",
        "trans fat",
        "cholesterol",
        "total carbohydrate",
        "vitamin d",
        "calcium",
        "iron",
        "potassium",
    }
    pattern = re.compile(
        r"\b([A-Z][A-Za-z ]{2,45}?)\s*[:\-]?\s*(<?\d+(?:\.\d+)?)\s*(g|mg|mcg|µg|iu|%)\b",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        label = re.sub(r"\s+", " ", match.group(1)).strip().lower()
        if label in known_labels or label.endswith(" calories"):
            continue
        unit = "mcg" if match.group(3).lower() == "µg" else match.group(3).lower()
        key = _normalize_nutrient_key(label, unit)
        if key in known_keys or key in additional:
            continue
        raw_value = match.group(2)
        value = float(raw_value.lstrip("<"))
        if raw_value.startswith("<"):
            additional[key] = f"<{value:g}{unit}"
        else:
            additional[key] = value
    return additional


def _serving_size(text: str) -> str | None:
    match = re.search(r"serving size\s*[:\-]?\s*([^.;\n]+)", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", match.group(1)).strip()[:80] if match else None


def _extract_nutrition(text: str) -> ProductNutrition:
    sodium_mg = _number(r"sodium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg", text)
    sodium_g = _number(r"sodium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g\b", text)
    cholesterol_mg = _number(r"cholesterol\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg", text)
    cholesterol_g = _number(r"cholesterol\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g\b", text)
    potassium_mg = _number(r"potassium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg", text)
    potassium_g = _number(r"potassium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g\b", text)
    vitamin_d_mcg = _number(r"vitamin d\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mcg", text)
    vitamin_d_iu = _number(r"vitamin d\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*iu", text)
    calcium_mg = _number(r"calcium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg", text)
    calcium_g = _number(r"calcium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g\b", text)
    iron_mg = _number(r"iron\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg", text)
    iron_g = _number(r"iron\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g\b", text)
    nutrition: ProductNutrition = {
        "serving_size": _serving_size(text),
        "calories": _number(r"\bcalories\s*[:\-]?\s*(\d+(?:\.\d+)?)", text),
        "total_sugar_g": _number(r"total sugars?\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g", text),
        "added_sugar_g": _number(r"added sugars?\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g", text)
        or _number(r"includes?\s+(\d+(?:\.\d+)?)\s*g\s*added sugars?", text),
        "fiber_g": _number(r"(?:dietary )?fiber\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g", text),
        "protein_g": _number(r"protein\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g", text),
        "sodium_mg": sodium_mg if sodium_mg is not None else sodium_g * 1000 if sodium_g is not None else None,
        "total_fat_g": _number(r"total fat\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g", text),
        "saturated_fat_g": _number(r"saturated fat\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g", text),
        "trans_fat_g": _number(r"trans fat\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g", text),
        "cholesterol_mg": cholesterol_mg
        if cholesterol_mg is not None
        else cholesterol_g * 1000
        if cholesterol_g is not None
        else None,
        "total_carbohydrate_g": _number(r"total carbohydrates?\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g", text),
        "vitamin_d_mcg": vitamin_d_mcg
        if vitamin_d_mcg is not None
        else vitamin_d_iu * 0.025
        if vitamin_d_iu is not None
        else None,
        "calcium_mg": calcium_mg if calcium_mg is not None else calcium_g * 1000 if calcium_g is not None else None,
        "iron_mg": iron_mg if iron_mg is not None else iron_g * 1000 if iron_g is not None else None,
        "potassium_mg": potassium_mg
        if potassium_mg is not None
        else potassium_g * 1000
        if potassium_g is not None
        else None,
        "additional_nutrients": {},
    }
    nutrition["additional_nutrients"] = _extract_additional_nutrients(text, set(nutrition))
    return nutrition


def _nutrition_has_label_facts(nutrition: ProductNutrition) -> bool:
    return any(nutrition[key] is not None for key in NUTRITION_KEYS - {"serving_size"})


def _product_name_from_result(query: str, result: dict) -> str:
    title = _title(result)
    if title:
        return re.split(r"[|-]", title)[0].strip()
    return query


def _candidate_from_result(result: dict, reason: str) -> ProductCandidate | None:
    url = result.get("url")
    if not url:
        return None
    return {
        "name": _product_name_from_result("", result),
        "brand": None,
        "label_source_url": url,
        "reason": reason,
    }


def _brand_from_url(url: str) -> str | None:
    host = hostname(url)
    parts = host.split(".")
    if len(parts) < 2:
        return None
    label = parts[-2]
    if label in {"com", "co", "org", "gov", "net"} and len(parts) >= 3:
        label = parts[-3]
    if label in {"walmart", "target", "kroger", "amazon", "instacart", "openfoodfacts", "nutritionix"}:
        return None
    return label.replace("-", " ").title()


def _query_terms_match(query: str, text: str) -> bool:
    query_words = [word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) > 2]
    lower = text.lower()
    if not query_words:
        return False
    return sum(1 for word in query_words if word in lower) >= max(1, len(query_words) - 1)


def _variant_mismatch(query: str, result: dict) -> str | None:
    query_lower = query.lower()
    blob = f"{_title(result)} {result.get('url') or ''}".lower()
    mismatches = [
        term
        for term in VARIANT_TERMS
        if re.search(rf"\b{re.escape(term)}\b", blob) and not re.search(rf"\b{re.escape(term)}\b", query_lower)
    ]
    return f"Result appears to be a different variant: {', '.join(mismatches[:2])}." if mismatches else None


def _score_result(query: str, result: dict, ingredients: list[str], nutrition: ProductNutrition) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    url = result.get("url") or ""
    source = classify_product_source(url)
    blob = _search_blob(result)

    if source:
        source_points = {"manufacturer": 45, "retailer": 25, "food_database": 25}[source.source_type]
        score += source_points
        reasons.append(f"{source.source_type} source")
    if _query_terms_match(query, blob):
        score += 30
        reasons.append("query terms match")
    if ingredients:
        score += 20
        reasons.append("ingredients present")
    if _nutrition_has_label_facts(nutrition):
        score += 20
        reasons.append("nutrition facts present")
    if _variant_mismatch(query, result):
        score -= 35
        reasons.append("variant mismatch")
    if any(term in blob for term in LOW_QUALITY_PRODUCT_TERMS):
        score -= 40
        reasons.append("low-quality product-page signal")

    return score, reasons


def _with_debug(resolution: ProductResolution, debug: DebugTrace | None) -> ProductResolution:
    if debug is not None:
        resolution["debug"] = debug
    return resolution


def _resolve_from_response(query: str, response: dict, debug_query: str, include_debug: bool) -> ProductResolution:
    candidates: list[ProductCandidate] = []
    evaluated = []
    debug: DebugTrace | None = (
        {
            "query": debug_query,
            "result_count": len(response.get("results", [])),
            "tavily_query_count": 1,
            "selected_source_url": None,
            "decisions": [],
        }
        if include_debug
        else None
    )

    for result in response.get("results", []):
        url = result.get("url") or ""
        source = classify_product_source(url)
        decision: dict[str, Any] = {
            "url": url,
            "title": _title(result),
            "selected": False,
            "reason": "",
        }
        if source is None:
            decision["reason"] = "Rejected: source is not an allowed manufacturer, retailer, or food database."
            if debug:
                debug["decisions"].append(decision)
            continue

        text = _text(result)
        variant_reason = _variant_mismatch(query, result)
        if not _query_terms_match(query, text):
            candidate = _candidate_from_result(result, "Source looked credible but product match was unclear.")
            if candidate:
                candidates.append(candidate)
            decision["reason"] = "Rejected: product-name terms did not clearly match result text."
            if debug:
                debug["decisions"].append(decision)
            continue

        ingredients = _extract_ingredients(text)
        nutrition = _extract_nutrition(text)
        score, score_reasons = _score_result(query, result, ingredients, nutrition)
        candidate = _candidate_from_result(
            result,
            variant_reason or "Credible source found, but ingredients or nutrition facts were incomplete.",
        )

        if candidate:
            candidates.append(candidate)
        evaluated.append((score, result, source, ingredients, nutrition, score_reasons, variant_reason))
        decision["reason"] = f"Scored {score}: {', '.join(score_reasons) or 'no useful signals'}."
        if debug:
            debug["decisions"].append(decision)

    evaluated.sort(key=lambda item: item[0], reverse=True)
    complete = [item for item in evaluated if item[3] and _nutrition_has_label_facts(item[4]) and not item[6]]
    if complete:
        top = complete[0]
        runner_up = complete[1] if len(complete) > 1 else None
        if runner_up and top[0] - runner_up[0] < 20:
            return _with_debug(
                {"status": "needs_confirmation", "query": query, "candidates": candidates[:3]},
                debug,
            )

        _, result, source, ingredients, nutrition, _, _ = top
        url = result.get("url") or ""
        if debug:
            debug["selected_source_url"] = url
            for decision in debug["decisions"]:
                if decision["url"] == url:
                    decision["selected"] = True
                    decision["reason"] = f"Selected: highest-ranked complete label source. {decision['reason']}"
        return _with_debug(
            {
                "status": "resolved",
                "product": {
                    "name": _product_name_from_result(query, result),
                    "brand": _brand_from_url(url),
                    "ingredients": ingredients,
                    "nutrition": nutrition,
                    "label_source_url": url,
                    "label_source_type": source.source_type,
                    "confidence": source.confidence,
                },
            },
            debug,
        )

    if candidates:
        return _with_debug({"status": "needs_confirmation", "query": query, "candidates": candidates[:3]}, debug)

    return _with_debug(
        {
            "status": "not_found",
            "query": query,
            "reason": "No credible source returned a clear product label with ingredients and nutrition facts.",
        },
        debug,
    )


async def resolve_product(
    product_name: str,
    *,
    client: TavilyClientProtocol | None = None,
    settings: ProductResolverSettings | None = None,
    include_debug: bool = False,
) -> ProductResolution:
    settings = settings or ProductResolverSettings()
    query_key = _normalize_query(product_name)
    if not query_key:
        return {"status": "not_found", "query": product_name, "reason": "Product name is empty."}

    cached = _CACHE.get(query_key)
    now = time.time()
    if cached and now - cached[0] < settings.ttl_seconds and not include_debug:
        return cached[1]

    client = client or _get_client()
    search_query = f'"{product_name.strip()}" ingredients nutrition facts'

    try:
        response = await asyncio.to_thread(
            client.search,
            query=search_query,
            include_answer=False,
            include_raw_content="text",
            max_results=settings.max_results,
            search_depth=settings.search_depth,
            timeout=settings.timeout_seconds,
        )
    except Exception as exc:
        raise ProductResolutionError("Product lookup failed. Try again later.") from exc

    resolution = _resolve_from_response(product_name, response, search_query, include_debug)
    if not include_debug:
        _CACHE[query_key] = (now, resolution)
    return resolution
