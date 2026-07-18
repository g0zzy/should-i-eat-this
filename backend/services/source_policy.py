"""Source-quality helpers for Tavily product and evidence lookups.

Environment:
  TAVILY_API_KEY must be present in backend/.env or the process environment.
  Search timeout/count/depth are configured by the caller settings dataclasses.

Behavior:
  Product-label facts are accepted only from plainly present Tavily result text.
  Scientific evidence is restricted to prioritized health domains and never uses
  Tavily's generated answer as a citation.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


MANUFACTURER_DOMAINS = {
    "chobani.com",
    "gatorade.com",
    "mars.com",
    "samsclub.com",
    "snickers.com",
    "snickers.co.uk",
    "snickerscanada.ca",
    "naturevalley.com",
    "generalmills.com",
    "oreo.com",
    "mondelezinternational.com",
}

RETAILER_DOMAINS = {
    "walmart.com",
    "target.com",
    "kroger.com",
    "instacart.com",
    "amazon.com",
    "safeway.com",
}

FOOD_DATABASE_DOMAINS = {
    "fdc.nal.usda.gov",
    "nutritionix.com",
    "openfoodfacts.org",
    "myfooddata.com",
}

EVIDENCE_DOMAIN_PRIORITY = {
    "diabetes.org": "professional_association",
    "heart.org": "professional_association",
    "who.int": "public_health",
    "nih.gov": "public_health",
    "ncbi.nlm.nih.gov": "peer_reviewed",
    "pubmed.ncbi.nlm.nih.gov": "peer_reviewed",
    "cdc.gov": "public_health",
    "fda.gov": "public_health",
    "nhs.uk": "public_health",
    "health.gov": "public_health",
    "eatright.org": "professional_association",
    "acsm.org": "professional_association",
    "sportsrd.org": "professional_association",
}


@dataclass(frozen=True)
class SourceClassification:
    source_type: str
    confidence: str


def hostname(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def domain_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def classify_product_source(url: str) -> SourceClassification | None:
    host = hostname(url)
    if any(domain_matches(host, domain) for domain in MANUFACTURER_DOMAINS):
        return SourceClassification("manufacturer", "high")
    if any(domain_matches(host, domain) for domain in RETAILER_DOMAINS):
        return SourceClassification("retailer", "medium")
    if any(domain_matches(host, domain) for domain in FOOD_DATABASE_DOMAINS):
        return SourceClassification("food_database", "medium")
    return None


def classify_evidence_source(url: str) -> str | None:
    host = hostname(url)
    for domain, source_type in EVIDENCE_DOMAIN_PRIORITY.items():
        if domain_matches(host, domain):
            return source_type
    return None


def evidence_domains_for_topic(topic: str) -> list[str]:
    if topic == "added_sugar":
        return ["diabetes.org", "cdc.gov", "heart.org", "nih.gov", "health.gov"]
    if topic == "peanut_allergy":
        return ["nih.gov", "cdc.gov", "nhs.uk"]
    if topic == "sodium":
        return ["heart.org", "cdc.gov", "who.int", "nih.gov", "health.gov"]
    if topic == "caffeine":
        return ["fda.gov", "nih.gov", "nhs.uk"]
    if topic in {"fiber", "protein"}:
        return ["health.gov", "nih.gov", "eatright.org"]
    if topic == "pre_exercise_fat_fiber":
        return ["acsm.org", "sportsrd.org", "nih.gov"]
    return list(EVIDENCE_DOMAIN_PRIORITY)
