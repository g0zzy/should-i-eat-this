"""Live standalone smoke test for the batched scientific-evidence stage.

Run from ``backend`` with ``python test_evidence.py``. This script does not
resolve product ingredients and does not call synthesis.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

from evidence import get_evidence

SAMPLE_INGREDIENTS = ["aspartame", "sucralose", "palm oil", "caramel color E150d"]
AUTHORITATIVE_DOMAINS = {
    "efsa.europa.eu",
    "fda.gov",
    "who.int",
    "ncbi.nlm.nih.gov",
    "nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
}


def _authoritative(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in AUTHORITATIVE_DOMAINS)


def main() -> None:
    result = get_evidence(SAMPLE_INGREDIENTS)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failures: list[str] = []
    if len(result) != len(SAMPLE_INGREDIENTS):
        failures.append("the output did not contain one object per ingredient")

    citation_count = 0
    for item in result:
        ingredient = item.get("ingredient", "unknown")
        if not item.get("summary"):
            failures.append(f"{ingredient}: summary is empty")
        evidence = item.get("evidence", [])
        if len(evidence) > 3:
            failures.append(f"{ingredient}: more than 3 evidence items were returned")
        for claim in evidence:
            citation_count += 1
            url = claim.get("source_url", "")
            if not _authoritative(url):
                failures.append(f"{ingredient}: non-authoritative URL returned: {url}")
            if not claim.get("claim"):
                failures.append(f"{ingredient}: an empty claim was returned")

    if citation_count == 0:
        failures.append("no real authoritative citations were returned")

    if failures:
        raise SystemExit("\nEvidence smoke test failed:\n- " + "\n- ".join(failures))

    print("\nEvidence smoke test passed; all accepted URLs came from the Tavily result allow-list.")


if __name__ == "__main__":
    main()
