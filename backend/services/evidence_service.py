"""Decision-relevant health evidence search for resolved products.

Requires TAVILY_API_KEY in backend/.env or the process environment. The service
keeps product-label facts separate from scientific evidence: product nutrition
triggers decide topics, and Tavily result URLs supply evidence citations.
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

from services.source_policy import (
    classify_evidence_source,
    evidence_domains_for_topic,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Evidence(TypedDict):
    topic: str
    status: NotRequired[Literal["found"]]
    product_trigger: str
    claim: str
    source_url: str
    source_title: str
    source_type: Literal[
        "clinical_guideline",
        "public_health",
        "peer_reviewed",
        "professional_association",
    ]
    relevance: Literal["high", "medium"]
    debug: NotRequired[dict[str, Any]]


class EvidenceGap(TypedDict):
    topic: str
    status: Literal["no_high_quality_source_found"]
    product_trigger: str
    reason: str
    relevance: Literal["high", "medium"]
    debug: NotRequired[dict[str, Any]]


class TavilyConfigurationError(RuntimeError):
    """Raised when Tavily cannot be configured safely."""


class EvidenceSearchError(RuntimeError):
    """Raised for user-safe Tavily evidence failures."""


class TavilyClientProtocol(Protocol):
    def search(self, **kwargs) -> dict:
        ...


@dataclass(frozen=True)
class EvidenceTopic:
    topic: str
    product_trigger: str
    query: str
    relevance: Literal["high", "medium"]


@dataclass
class EvidenceSettings:
    ttl_seconds: int = int(os.getenv("EVIDENCE_CACHE_TTL_SECONDS", "900"))
    max_results: int = int(os.getenv("TAVILY_EVIDENCE_MAX_RESULTS", "4"))
    timeout_seconds: float = float(os.getenv("TAVILY_TIMEOUT_SECONDS", "12"))
    search_depth: str = os.getenv("TAVILY_SEARCH_DEPTH", "basic")


EvidenceResult = Evidence | EvidenceGap

_CACHE: dict[str, tuple[float, list[EvidenceResult]]] = {}


def _get_client() -> TavilyClientProtocol:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise TavilyConfigurationError("TAVILY_API_KEY is missing. Add it to backend/.env.")

    from tavily import TavilyClient

    return TavilyClient(api_key=api_key)


def _profile_values(profile: dict, key: str) -> list[str]:
    values = profile.get(key) or []
    if isinstance(values, str):
        return [values]
    return [str(value) for value in values]


def _has_profile_term(profile: dict, *terms: str) -> bool:
    haystack = " ".join(
        _profile_values(profile, "health_conditions")
        + _profile_values(profile, "allergies_or_intolerances")
        + _profile_values(profile, "dietary_goals")
        + _profile_values(profile, "personal_rules")
    ).lower()
    return any(term in haystack for term in terms)


def _ingredients(product: dict) -> list[str]:
    return [str(item).lower() for item in product.get("ingredients", [])]


def _nutrition(product: dict, key: str) -> float | None:
    value = (product.get("nutrition") or {}).get(key)
    return value if isinstance(value, int | float) else None


def _derive_topics(product: dict, profile: dict) -> list[EvidenceTopic]:
    topics: list[EvidenceTopic] = []
    ingredients = _ingredients(product)
    added_sugar = _nutrition(product, "added_sugar_g")
    total_sugar = _nutrition(product, "total_sugar_g")
    sodium = _nutrition(product, "sodium_mg")
    fiber = _nutrition(product, "fiber_g")
    protein = _nutrition(product, "protein_g")
    total_fat = _nutrition(product, "total_fat_g")

    sugar_value = added_sugar if added_sugar is not None else total_sugar
    if sugar_value is not None and sugar_value >= 10 and _has_profile_term(
        profile, "diabetes", "type_2_diabetes", "added sugar", "limit_added_sugar", "blood sugar"
    ):
        label = "added sugar" if added_sugar is not None else "total sugar"
        topics.append(
            EvidenceTopic(
                "added_sugar",
                f"{sugar_value:g}g {label} per serving",
                "added sugar type 2 diabetes clinical guideline",
                "high",
            )
        )

    allergy_terms = _profile_values(profile, "allergies_or_intolerances")
    for allergy in allergy_terms:
        normalized = allergy.lower().strip()
        if normalized and any(normalized.rstrip("s") in ingredient for ingredient in ingredients):
            topics.append(
                EvidenceTopic(
                    f"{normalized.rstrip('s')}_allergy",
                    f"{allergy} appears in the ingredient list",
                    f"{allergy} allergy avoidance guideline",
                    "high",
                )
            )

    if sodium is not None and sodium >= 400 and _has_profile_term(profile, "hypertension", "blood pressure", "sodium"):
        topics.append(
            EvidenceTopic(
                "sodium",
                f"{sodium:g}mg sodium per serving",
                "sodium hypertension dietary guideline",
                "high",
            )
        )

    if any("caffeine" in ingredient for ingredient in ingredients) and _has_profile_term(profile, "caffeine"):
        topics.append(
            EvidenceTopic(
                "caffeine",
                "caffeine appears in the ingredient list",
                "caffeine sensitivity clinical guidance",
                "high",
            )
        )

    if fiber is not None and fiber < 3 and _has_profile_term(profile, "fiber", "increase_fiber"):
        topics.append(
            EvidenceTopic("fiber", f"{fiber:g}g fiber per serving", "dietary fiber intake health guideline", "medium")
        )

    if protein is not None and protein < 5 and _has_profile_term(profile, "protein", "increase_protein"):
        topics.append(
            EvidenceTopic("protein", f"{protein:g}g protein per serving", "dietary protein intake guideline", "medium")
        )

    if any("palm oil" in ingredient for ingredient in ingredients) and _has_profile_term(
        profile, "heart", "cardiovascular", "saturated fat", "cholesterol"
    ):
        topics.append(
            EvidenceTopic(
                "palm_oil",
                "palm oil appears in the ingredient list",
                "palm oil cardiovascular health evidence guideline",
                "medium",
            )
        )

    if total_fat is not None and total_fat >= 8 and _has_profile_term(
        profile, "endurance", "run", "exercise", "pre-run", "training"
    ):
        topics.append(
            EvidenceTopic(
                "pre_exercise_fat_fiber",
                f"{total_fat:g}g total fat per serving",
                "high fat food before endurance exercise gastrointestinal distress guideline",
                "medium",
            )
        )

    deduped: dict[str, EvidenceTopic] = {}
    for topic in topics:
        deduped.setdefault(topic.topic, topic)
    return list(deduped.values())


def _cache_key(topic: EvidenceTopic) -> str:
    return f"{topic.topic}|{topic.product_trigger.lower()}|{topic.relevance}"


def _text(result: dict) -> str:
    return " ".join(
        str(result.get(key, "")) for key in ("title", "content", "raw_content") if result.get(key)
    )


def _short_claim(topic: EvidenceTopic, result: dict) -> str:
    text = _text(result).lower()
    if topic.topic == "added_sugar":
        if "diabetes" in text:
            return "Diabetes guidance recommends limiting sugar-sweetened foods and drinks to support blood-glucose management."
        return "Public-health guidance recommends limiting added sugar intake as part of a healthy diet."
    if topic.topic.endswith("_allergy"):
        allergen = topic.topic.removesuffix("_allergy").replace("_", " ")
        return f"Allergy guidance recommends avoiding foods that contain {allergen} when a person has that allergy."
    if topic.topic == "sodium":
        return "Cardiovascular guidance links lower sodium intake with better blood-pressure control for people at risk."
    if topic.topic == "caffeine":
        return "Health guidance notes that caffeine-sensitive people may need to limit caffeine-containing products."
    if topic.topic == "fiber":
        return "Dietary guidance identifies fiber as an important nutrient that many people should increase."
    if topic.topic == "protein":
        return "Dietary guidance discusses protein intake as relevant to satiety and daily nutrient adequacy."
    if topic.topic == "pre_exercise_fat_fiber":
        return "Sports-nutrition guidance commonly cautions that higher-fat foods close to exercise can slow digestion."
    return "Credible health guidance discusses this product factor as relevant to the user's profile."


async def _search_topic(
    topic: EvidenceTopic,
    client: TavilyClientProtocol,
    settings: EvidenceSettings,
    include_debug: bool,
) -> list[EvidenceResult]:
    include_domains = evidence_domains_for_topic(topic.topic)
    query = topic.query
    response = await asyncio.to_thread(
        client.search,
        query=query,
        include_answer=False,
        include_raw_content="text",
        include_domains=include_domains,
        max_results=settings.max_results,
        search_depth=settings.search_depth,
        timeout=settings.timeout_seconds,
    )

    evidence: list[Evidence] = []
    seen_urls = set()
    decisions: list[dict[str, Any]] = []
    for result in response.get("results", []):
        url = result.get("url")
        decision: dict[str, Any] = {
            "url": url,
            "title": str(result.get("title") or "").strip(),
            "selected": False,
            "reason": "",
        }
        if not url or url in seen_urls:
            decision["reason"] = "Rejected: missing URL or duplicate URL."
            decisions.append(decision)
            continue
        source_type = classify_evidence_source(url)
        if source_type is None:
            decision["reason"] = "Rejected: domain is not in the credible evidence allowlist."
            decisions.append(decision)
            continue
        decision["selected"] = True
        decision["reason"] = f"Selected: {source_type} source on an allowed evidence domain."
        decisions.append(decision)
        evidence.append(
            {
                "topic": topic.topic,
                "status": "found",
                "product_trigger": topic.product_trigger,
                "claim": _short_claim(topic, result),
                "source_url": url,
                "source_title": str(result.get("title") or "").strip(),
                "source_type": source_type,
                "relevance": topic.relevance,
            }
        )
        seen_urls.add(url)
        if len(evidence) == 2:
            break

    debug = {
        "query": query,
        "included_domains": include_domains,
        "result_count": len(response.get("results", [])),
        "tavily_query_count": 1,
        "selected_source_urls": [item["source_url"] for item in evidence],
        "decisions": decisions,
    }
    if evidence:
        if include_debug:
            for item in evidence:
                item["debug"] = debug
        return evidence

    gap: EvidenceGap = {
        "topic": topic.topic,
        "status": "no_high_quality_source_found",
        "product_trigger": topic.product_trigger,
        "reason": "No prioritized clinical/public-health source found.",
        "relevance": topic.relevance,
    }
    if include_debug:
        gap["debug"] = debug
    return [gap]


async def find_relevant_evidence(
    product: dict,
    profile: dict,
    *,
    client: TavilyClientProtocol | None = None,
    settings: EvidenceSettings | None = None,
    include_debug: bool = False,
) -> list[EvidenceResult]:
    settings = settings or EvidenceSettings()
    topics = _derive_topics(product, profile)
    if not topics:
        return []

    client = client or _get_client()
    now = time.time()
    output: list[EvidenceResult] = []

    for topic in topics:
        key = _cache_key(topic)
        cached = _CACHE.get(key)
        if cached and now - cached[0] < settings.ttl_seconds and not include_debug:
            output.extend(cached[1])
            continue

        try:
            evidence = await _search_topic(topic, client, settings, include_debug)
        except Exception as exc:
            raise EvidenceSearchError("Evidence lookup failed. Try again later.") from exc

        if not include_debug:
            _CACHE[key] = (now, evidence)
        output.extend(evidence)

    return output
