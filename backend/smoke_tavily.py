"""Live Tavily smoke test for product resolution and evidence retrieval.

Usage:
  python backend/smoke_tavily.py "Snickers" diabetic

The script loads TAVILY_API_KEY from backend/.env via the service modules. It
prints source URLs and debug counts, but never prints secrets.
"""
from __future__ import annotations

import asyncio
import json
import sys

from services.evidence_service import find_relevant_evidence
from services.product_resolver import resolve_product


PROFILES = {
    "diabetic": {
        "health_conditions": ["type_2_diabetes"],
        "allergies_or_intolerances": [],
        "dietary_goals": ["limit_added_sugar", "increase_fiber"],
        "personal_rules": ["Avoid snacks with more than 15g added sugar"],
    },
    "athlete": {
        "health_conditions": [],
        "allergies_or_intolerances": [],
        "dietary_goals": ["quick_carbs_near_training"],
        "personal_rules": ["Avoid high-fat or high-fiber foods within 2 hours of a run"],
    },
    "peanut_allergy": {
        "health_conditions": [],
        "allergies_or_intolerances": ["peanuts"],
        "dietary_goals": [],
        "personal_rules": ["Avoid any product containing peanuts"],
    },
    "hypertension": {
        "health_conditions": ["hypertension"],
        "allergies_or_intolerances": [],
        "dietary_goals": ["limit_sodium"],
        "personal_rules": ["Avoid high-sodium snacks"],
    },
}


def _query_count_from_debug(items: list[dict]) -> int:
    seen_queries = set()
    for item in items:
        debug = item.get("debug") or {}
        query = debug.get("query")
        if query:
            seen_queries.add(query)
    return len(seen_queries)


async def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: python backend/smoke_tavily.py "Snickers" diabetic')
        return 2

    product_name = sys.argv[1]
    profile_name = sys.argv[2] if len(sys.argv) > 2 else "diabetic"
    profile = PROFILES.get(profile_name)
    if profile is None:
        print(f"Unknown profile '{profile_name}'. Available: {', '.join(PROFILES)}")
        return 2

    resolution = await resolve_product(product_name, include_debug=True)
    print("Product resolution:")
    print(json.dumps(resolution, indent=2))

    if resolution["status"] != "resolved":
        return 1

    evidence = await find_relevant_evidence(resolution["product"], profile, include_debug=True)
    print("\nEvidence and gaps:")
    print(json.dumps(evidence, indent=2))

    product_query_count = (resolution.get("debug") or {}).get("tavily_query_count", 0)
    evidence_query_count = _query_count_from_debug(evidence)
    print("\nTavily query count:")
    print(json.dumps({"product_resolution": product_query_count, "evidence": evidence_query_count}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
