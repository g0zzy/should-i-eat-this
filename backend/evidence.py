"""Live web evidence lookup, backed by Tavily.

Tavily docs: https://docs.tavily.com
"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

_CACHE: dict[str, dict] = {}

_PLAIN_INGREDIENTS = {
    "water",
    "whole grain oats",
    "oats",
    "canola oil",
    "salt",
    "cultured pasteurized whole milk",
    "live active cultures",
    "baking soda",
}

_NOTABLE_TERMS = {
    "sugar",
    "syrup",
    "dextrose",
    "honey",
    "lecithin",
    "color",
    "yellow",
    "blue",
    "red",
    "preservative",
    "citrate",
    "phosphate",
    "acid",
    "flavor",
    "sodium",
    "potassium",
}

_CONCERN_TERMS = {
    "fda",
    "efsa",
    "regulator",
    "regulatory",
    "study",
    "review",
    "risk",
    "safe",
    "safety",
    "acceptable daily intake",
    "adi",
    "diabetes",
    "glucose",
    "blood sugar",
    "glycemic",
    "cardiovascular",
    "metabolic",
    "additive",
    "color additive",
    "allergy",
    "intolerance",
    "inflammation",
    "exposure",
}


def _is_notable(ingredient: str) -> bool:
    normalized = ingredient.strip().lower()
    if not normalized or normalized in _PLAIN_INGREDIENTS:
        return False
    if normalized == "palm oil":
        return True
    return any(term in normalized for term in _NOTABLE_TERMS)


def _ingredient_keywords(ingredient: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", ingredient.lower())
    return [word for word in words if len(word) > 2]


def _chunk_ingredients(ingredients: list[str]) -> list[list[str]]:
    if len(ingredients) <= 4:
        return [ingredients]

    midpoint = (len(ingredients) + 1) // 2
    return [ingredients[:midpoint], ingredients[midpoint:]]


def _build_query(batch: list[str]) -> str:
    joined = ", ".join(batch)
    return (
        "current nutrition science and regulator evidence for these food "
        f"ingredients: {joined}. Focus on health effects, FDA, EFSA, acceptable "
        "daily intake, diabetes, metabolic effects, and food additive safety."
    )


def _result_text(result: dict) -> str:
    return " ".join(
        str(result.get(key, "")) for key in ("title", "content", "raw_content") if result.get(key)
    )


def _matches_ingredient(ingredient: str, result: dict) -> bool:
    text = _result_text(result).lower()
    keywords = _ingredient_keywords(ingredient)
    if not keywords:
        return False

    if ingredient.lower() in text:
        return True

    return any(keyword in text for keyword in keywords)


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", cleaned) if sentence.strip()]


def _best_sentence(ingredient: str, result: dict) -> str:
    keywords = _ingredient_keywords(ingredient)
    sentences = _split_sentences(_result_text(result))

    def score(sentence: str) -> int:
        lower = sentence.lower()
        ingredient_score = sum(3 for keyword in keywords if keyword in lower)
        concern_score = sum(1 for term in _CONCERN_TERMS if term in lower)
        return ingredient_score + concern_score

    ranked = sorted(sentences, key=score, reverse=True)
    return ranked[0] if ranked else _result_text(result)


def _paraphrase_claim(ingredient: str, result: dict) -> str:
    text = _best_sentence(ingredient, result).lower()
    name = ingredient.strip()

    if any(term in text for term in ("efsa", "acceptable daily intake", "adi")):
        return f"European safety material discusses {name} using exposure limits or acceptable-intake framing."
    if "fda" in text or "color additive" in text or "gras" in text:
        return f"U.S. regulatory material discusses {name} as a permitted or reviewed food ingredient."
    if any(term in text for term in ("diabetes", "glucose", "blood sugar", "glycemic")):
        return f"Clinical or public-health material links {name} with blood-sugar or metabolic considerations."
    if any(term in text for term in ("sugar", "sweetened", "added sugar", "syrup")):
        return f"Nutrition guidance treats {name} as an added-sugar source to limit in routine diets."
    if any(term in text for term in ("allergy", "allergic", "sensitivity", "intolerance")):
        return f"Safety material notes possible sensitivity or intolerance concerns for {name} in some people."
    if any(term in text for term in ("safe", "safety", "risk", "review")):
        return f"Safety reviews discuss {name} in the context of food-additive exposure and risk."

    return f"Source material discusses {name} in relation to food safety or nutrition."


def _summary_for(ingredient: str, claims: list[str], answer: str | None) -> str:
    name = ingredient.strip()
    lower_name = name.lower()

    if answer and lower_name in answer.lower():
        compact = re.sub(r"\s+", " ", answer).strip()
        sentences = _split_sentences(compact)
        relevant = [s for s in sentences if lower_name in s.lower()]
        if relevant:
            return " ".join(relevant[:2])[:420]

    if not claims:
        return f"{name} is a notable ingredient, but the live search did not return a usable citation."

    if len(claims) == 1:
        return claims[0]

    return f"Current sources discuss {name} from both nutrition and food-safety angles. The strongest live citations cover {claims[0][0].lower() + claims[0][1:]}"


def _empty_entry(ingredient: str) -> dict:
    return {"ingredient": ingredient, "summary": "", "evidence": []}


async def get_evidence(ingredients: list[str]) -> list[dict]:
    """Search the web for evidence about the given ingredients.

    Args:
        ingredients: list of ingredient name strings from a product.

    Returns:
        A list of ingredient evidence dicts. Plain ingredients are skipped.
    """
    notable = [ingredient for ingredient in ingredients if _is_notable(ingredient)]
    if not notable:
        return []

    missing = []
    for ingredient in notable:
        cached = _CACHE.get(ingredient.lower())
        if cached is None:
            missing.append(ingredient)

    if not missing:
        return [_CACHE[ingredient.lower()] for ingredient in notable]

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        for ingredient in missing:
            entry = _empty_entry(ingredient)
            _CACHE[ingredient.lower()] = entry
        return [_CACHE[ingredient.lower()] for ingredient in notable]

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
    except Exception:
        for ingredient in missing:
            entry = _empty_entry(ingredient)
            _CACHE[ingredient.lower()] = entry
        return [_CACHE[ingredient.lower()] for ingredient in notable]

    for batch in _chunk_ingredients(missing):
        try:
            response = client.search(
                query=_build_query(batch),
                include_answer=True,
                max_results=3,
            )
        except Exception:
            for ingredient in batch:
                entry = _empty_entry(ingredient)
                _CACHE[ingredient.lower()] = entry
            continue

        answer = response.get("answer") if isinstance(response, dict) else None
        results = response.get("results", []) if isinstance(response, dict) else []

        for ingredient in batch:
            evidence = []
            seen_urls = set()

            for result in results:
                source_url = result.get("url")
                if not source_url or source_url in seen_urls:
                    continue
                if not _matches_ingredient(ingredient, result):
                    continue

                evidence.append(
                    {
                        "claim": _paraphrase_claim(ingredient, result),
                        "source_url": source_url,
                    }
                )
                seen_urls.add(source_url)

                if len(evidence) == 3:
                    break

            claims = [item["claim"] for item in evidence]
            entry = {
                "ingredient": ingredient,
                "summary": _summary_for(ingredient, claims, answer),
                "evidence": evidence,
            }
            _CACHE[ingredient.lower()] = entry

    return [_CACHE[ingredient.lower()] for ingredient in notable]
