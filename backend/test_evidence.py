"""Standalone verifier for the Tavily-backed evidence layer."""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

from evidence import get_evidence

BACKEND_DIR = Path(__file__).parent
SEED_DIR = Path(__file__).parent / "seed"

load_dotenv(BACKEND_DIR / ".env")


def _split_ingredients(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    match = re.search(
        r"ingredients?\s*(?:list)?\s*[:\-]\s*(.+?)(?:\.| contains | allergen| nutrition|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"(?:contains|includes?|made with)\s+(.+?)(?:\.| allergen| nutrition|$)",
            text,
            flags=re.IGNORECASE,
        )

    source = match.group(1) if match else text
    source = re.sub(r"\s+and\s+", ", ", source, flags=re.IGNORECASE)
    ingredients = []
    for item in source.split(","):
        cleaned = item.strip(" .;:()[]")
        cleaned = re.sub(r"^(and|or|plus|with)\s+", "", cleaned, flags=re.IGNORECASE)
        if re.search(r"\b(check|label|website|accurate|typically|usually)\b", cleaned, re.IGNORECASE):
            continue
        if 2 < len(cleaned) <= 80:
            ingredients.append(cleaned)

    return ingredients[:25]


def get_product_ingredients(product_name: str) -> list[str]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is missing. Add it to backend/.env.")

    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=f"{product_name} official ingredients list food label",
        include_answer=True,
        max_results=3,
    )

    answer = response.get("answer") or ""
    ingredients = _split_ingredients(answer)
    if ingredients:
        return ingredients

    for result in response.get("results", []):
        ingredients = _split_ingredients(result.get("content", ""))
        if ingredients:
            return ingredients

    return []


async def main() -> None:
    product_names = sys.argv[1:]
    if product_names:
        for product_name in product_names:
            ingredients = get_product_ingredients(product_name)
            print(f"\n=== {product_name} ===")
            print("Ingredients:")
            print(json.dumps(ingredients, indent=2))
            print("Evidence:")
            print(json.dumps(await get_evidence(ingredients), indent=2))
        return

    with open(SEED_DIR / "products.json") as f:
        products = json.load(f)

    for product in products:
        evidence = await get_evidence(product["ingredients"])
        print(f"\n=== {product['name']} ===")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
