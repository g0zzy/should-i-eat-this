"""Resolve product ingredients, then reduce them to evidence-worthy items.

This module deliberately stops before scientific evidence retrieval.  Its two
public functions return plain Python data and degrade safely when either Tavily
or the configured LLM is unavailable.
"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient

load_dotenv(Path(__file__).with_name(".env"))

_KNOWN_DOMAINS = {"world.openfoodfacts.org"}
_GERMAN_PRODUCT_HINTS = {
    "aldi",
    "edeka",
    "kaufland",
    "lidl",
    "netto",
    "rewe",
    "rossmann",
}
_RESOLUTION_CACHE: dict[str, dict] = {}

_PARSE_SYSTEM_PROMPT = (
    "Extract ONLY the ingredient list as a JSON array of strings. "
    "If no ingredient list is present, return []. No prose."
)
_FILTER_SYSTEM_PROMPT = """Return ONLY a JSON array of strings selected from the input list.
Keep additives, artificial sweeteners, preservatives, colorings/dyes including E-numbers,
palm oil, seed oils, added sugars and syrups, flavor enhancers, and nutritionally notable
items. Drop basic whole foods and neutral ingredients such as water, salt or sea salt,
oats, flour, and common spices. Handle English and German ingredient names, including
Zucker, Palmöl, Säuerungsmittel, Farbstoff, Konservierungsstoff, and Geschmacksverstärker.
Copy kept strings exactly from the input. Do not add, translate, explain, or rewrite items."""


def _none_result(product_name: str) -> dict:
    return {
        "product_name": product_name,
        "ingredients": [],
        "source_url": "",
        "source_type": "none",
        "confidence": "low",
    }


def _cache_key(product_name: str) -> str:
    return product_name.strip().lower()


def _query_for(product_name: str) -> str:
    normalized = product_name.casefold()
    looks_german = any(hint in normalized.split() for hint in _GERMAN_PRODUCT_HINTS)
    looks_german = looks_german or bool(re.search(r"[äöüß]", normalized))
    suffix = "Zutaten" if looks_german else "ingredients"
    return f"{product_name} {suffix}"


def _valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _known_domain(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in _KNOWN_DOMAINS)


def _has_clear_ingredient_list(text: object) -> bool:
    if not isinstance(text, str):
        return False
    normalized = re.sub(r"\s+", " ", text).casefold()
    has_heading = any(marker in normalized for marker in ("ingredients", "ingredient list", "zutaten"))
    return has_heading and len(normalized) >= 80 and ("," in normalized or ":" in normalized)


def _ingredient_context(page_text: str) -> str:
    """Narrow a product page to its ingredient section before the small LLM call."""
    heading = re.search(r"(?im)^#{1,5}\s+(?:ingredients|zutaten)\b", page_text)
    if not heading:
        return page_text[:12000]
    return page_text[heading.start():heading.start() + 6000]


def _extracted_text(response: object) -> str:
    if not isinstance(response, dict):
        return ""
    results = response.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return ""
    result = results[0]
    for field in ("raw_content", "content"):
        value = result.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _llm_text(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured")

    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    if provider == "anthropic":
        response = Anthropic(api_key=api_key).messages.create(
            model="claude-haiku-4-5",
            max_tokens=1200,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        )

    if provider == "openai":
        response = OpenAI(api_key=api_key).chat.completions.create(
            model="gpt-4.1-nano",
            max_tokens=1200,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def _json_array(text: str) -> list[str]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)

    start = stripped.find("[")
    end = stripped.rfind("]")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON array")

    payload = json.loads(stripped[start:end + 1])
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise ValueError("LLM response was not a JSON string array")
    return payload


def _clean_items(items: list[str], *, lowercase: bool = False) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = re.sub(r"\s+", " ", item).strip(" \t\r\n,;•")
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        cleaned.append(value.lower() if lowercase else value)
    return cleaned


def _clean_parse(ingredients: list[str]) -> bool:
    if len(ingredients) < 3:
        return False
    weak_values = {"ingredient", "ingredients", "ingredient list", "zutaten", "unknown"}
    return all(
        1 < len(item) <= 160
        and "\n" not in item
        and item.casefold() not in weak_values
        for item in ingredients
    )


def resolve_ingredients(product_name: str) -> dict:
    """Resolve a product name to a parsed ingredient list using Tavily and one LLM call."""
    normalized_name = product_name.strip()
    key = _cache_key(normalized_name)
    if key in _RESOLUTION_CACHE:
        return deepcopy(_RESOLUTION_CACHE[key])

    failure = _none_result(normalized_name)
    if not normalized_name or not os.getenv("TAVILY_API_KEY"):
        _RESOLUTION_CACHE[key] = failure
        return deepcopy(failure)

    try:
        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        search = client.search(
            query=_query_for(normalized_name),
            search_depth="advanced",
            max_results=5,
            include_raw_content=True,
            include_domains=["world.openfoodfacts.org"],
            country="germany",
        )
        results = search.get("results") if isinstance(search, dict) else None
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            raise ValueError("Tavily returned no product results")

        best_result = results[0]
        source_url = best_result.get("url")
        if not isinstance(source_url, str) or not _valid_url(source_url):
            raise ValueError("Tavily returned an invalid source URL")

        raw_content = best_result.get("raw_content")
        if _has_clear_ingredient_list(raw_content):
            page_text = raw_content
        else:
            extracted = client.extract(urls=[source_url], extract_depth="advanced")
            page_text = _extracted_text(extracted)
        if not page_text:
            raise ValueError("No page text was available for ingredient parsing")

        llm_output = _llm_text(
            _PARSE_SYSTEM_PROMPT,
            f"Product: {normalized_name}\nPage ingredient section:\n{_ingredient_context(page_text)}",
        )
        ingredients = _clean_items(_json_array(llm_output))
        if not ingredients:
            raise ValueError("No ingredients were present in the parsed page")

        result = {
            "product_name": normalized_name,
            "ingredients": ingredients,
            "source_url": source_url,
            "source_type": "web",
            "confidence": "high" if _known_domain(source_url) and _clean_parse(ingredients) else "low",
        }
    except Exception:
        result = failure

    _RESOLUTION_CACHE[key] = result
    return deepcopy(result)


def filter_notable(ingredients: list[str]) -> list[str]:
    """Use one LLM call to retain only ingredients worth checking for health evidence."""
    if not ingredients:
        return []

    original = list(ingredients)
    try:
        llm_output = _llm_text(
            _FILTER_SYSTEM_PROMPT,
            f"Ingredient list:\n{json.dumps(ingredients, ensure_ascii=False)}",
        )
        selected = _json_array(llm_output)

        allowed = {item.casefold() for item in _clean_items(ingredients)}
        filtered = [item for item in _clean_items(selected, lowercase=True) if item.casefold() in allowed]
        return _clean_items(filtered, lowercase=True)
    except Exception:
        return original
