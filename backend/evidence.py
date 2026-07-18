"""Batched, cited health-evidence lookup for already-filtered ingredients.

This module does not resolve product labels and does not produce a verdict. It
accepts notable ingredient names and returns only claims attributed to URLs in
one authoritative-domain Tavily response.
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

_AUTHORITATIVE_DOMAINS = (
    "efsa.europa.eu",
    "fda.gov",
    "who.int",
    "ncbi.nlm.nih.gov",
    "nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
)
_CACHE: dict[tuple[str, ...], list[dict]] = {}

_SYSTEM_PROMPT = """For each ingredient, write a 1-2 sentence neutral summary of
what the evidence says and attach up to 3 claims, each with the source_url of
the result it came from. Note EFSA/FDA disagreement when the provided sources
show one. Use ONLY the provided results; never invent a URL or a source. Keep
claims short and paraphrased, never long verbatim quotes. If there is no evidence
for an ingredient, give an empty evidence list and a summary saying evidence was
limited. Return ONLY valid JSON matching this schema, with no prose or markdown:
[{"ingredient": "string", "summary": "string", "evidence":
[{"claim": "string", "source_url": "exact URL from a provided result"}]}]"""


def _clean_ingredients(ingredients: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for ingredient in ingredients:
        value = re.sub(r"\s+", " ", str(ingredient)).strip()
        key = value.casefold()
        if value and key not in seen:
            cleaned.append(value)
            seen.add(key)
    return cleaned


def _cache_key(ingredients: list[str]) -> tuple[str, ...]:
    return tuple(sorted(ingredient.casefold() for ingredient in ingredients))


def _limited_entry(ingredient: str) -> dict:
    return {
        "ingredient": ingredient,
        "summary": f"Evidence was limited for {ingredient} in the retrieved authoritative sources.",
        "evidence": [],
    }


def _failure_entries(ingredients: list[str]) -> list[dict]:
    return [
        {
            "ingredient": ingredient,
            "summary": f"Could not retrieve evidence for {ingredient}.",
            "evidence": [],
        }
        for ingredient in ingredients
    ]


def _authoritative_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in _AUTHORITATIVE_DOMAINS
    )


def _result_payload(response: object) -> list[dict[str, str]]:
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        return []

    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in response["results"]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or url in seen_urls or not _authoritative_url(url):
            continue
        title = item.get("title") if isinstance(item.get("title"), str) else ""
        content = item.get("content") if isinstance(item.get("content"), str) else ""
        results.append(
            {
                "title": re.sub(r"\s+", " ", title).strip()[:300],
                "url": url,
                "content": re.sub(r"\s+", " ", content).strip()[:3500],
            }
        )
        seen_urls.add(url)
    return results


def _llm_text(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured")

    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    if provider == "anthropic":
        response = Anthropic(api_key=api_key).messages.create(
            model="claude-haiku-4-5",
            max_tokens=2400,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        )

    if provider == "openai":
        response = OpenAI(api_key=api_key).chat.completions.create(
            model="gpt-4.1-nano",
            max_tokens=2400,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def _parse_json(text: str) -> list[dict]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)

    start = stripped.find("[")
    end = stripped.rfind("]")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON array")

    payload = json.loads(stripped[start:end + 1])
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("LLM response did not match the evidence array schema")
    return payload


def _compact_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= limit:
        return compact
    shortened = compact[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened}…" if shortened else ""


def _validated_entries(
    ingredients: list[str],
    payload: list[dict],
    allowed_urls: set[str],
) -> list[dict]:
    requested = {ingredient.casefold(): ingredient for ingredient in ingredients}
    returned: dict[str, dict] = {}
    for item in payload:
        ingredient = item.get("ingredient")
        if not isinstance(ingredient, str):
            continue
        key = ingredient.strip().casefold()
        if key in requested and key not in returned:
            returned[key] = item

    if ingredients and not returned:
        raise ValueError("LLM response did not contain any requested ingredients")

    validated: list[dict] = []
    for ingredient in ingredients:
        item = returned.get(ingredient.casefold())
        if item is None:
            validated.append(_limited_entry(ingredient))
            continue

        raw_evidence = item.get("evidence")
        evidence: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        if isinstance(raw_evidence, list):
            for claim_item in raw_evidence:
                if not isinstance(claim_item, dict):
                    continue
                url = claim_item.get("source_url")
                claim = _compact_text(claim_item.get("claim"), 280)
                if not isinstance(url, str) or url not in allowed_urls or not claim:
                    continue
                identity = (claim.casefold(), url)
                if identity in seen:
                    continue
                evidence.append({"claim": claim, "source_url": url})
                seen.add(identity)
                if len(evidence) == 3:
                    break

        if not evidence:
            validated.append(_limited_entry(ingredient))
            continue

        summary = _compact_text(item.get("summary"), 520)
        if not summary:
            summary = f"The retrieved authoritative sources contain evidence relevant to {ingredient}."
        validated.append(
            {
                "ingredient": ingredient,
                "summary": summary,
                "evidence": evidence,
            }
        )
    return validated


def _attribution_prompt(ingredients: list[str], answer: str, results: list[dict]) -> str:
    return json.dumps(
        {
            "ingredients": ingredients,
            "tavily_answer": answer[:6000],
            "results": results,
        },
        ensure_ascii=False,
    )


def get_evidence(ingredients: list[str]) -> list[dict]:
    """Return per-ingredient health evidence from one batched Tavily search."""
    normalized = _clean_ingredients(ingredients)
    if not normalized:
        return []

    key = _cache_key(normalized)
    if key in _CACHE:
        return deepcopy(_CACHE[key])

    fallback = _failure_entries(normalized)
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        _CACHE[key] = fallback
        return deepcopy(fallback)

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=f"health effects and safety evidence: {', '.join(normalized)}",
            search_depth="advanced",
            topic="general",
            max_results=6,
            include_answer="advanced",
            include_domains=list(_AUTHORITATIVE_DOMAINS),
        )
    except Exception:
        _CACHE[key] = fallback
        return deepcopy(fallback)

    results = _result_payload(response)
    allowed_urls = {result["url"] for result in results}
    answer = response.get("answer") if isinstance(response, dict) else ""
    answer = answer if isinstance(answer, str) else ""
    prompt = _attribution_prompt(normalized, answer, results)

    try:
        llm_output = _llm_text(_SYSTEM_PROMPT, prompt)
    except Exception:
        _CACHE[key] = fallback
        return deepcopy(fallback)

    try:
        payload = _parse_json(llm_output)
        evidence = _validated_entries(normalized, payload, allowed_urls)
    except (json.JSONDecodeError, TypeError, ValueError):
        retry_prompt = (
            f"The previous output was invalid. Return only the required JSON array.\n"
            f"Original data:\n{prompt}\nInvalid output:\n{llm_output[:4000]}"
        )
        try:
            retry_output = _llm_text(_SYSTEM_PROMPT, retry_prompt)
            payload = _parse_json(retry_output)
            evidence = _validated_entries(normalized, payload, allowed_urls)
        except Exception:
            evidence = fallback

    _CACHE[key] = evidence
    return deepcopy(evidence)
