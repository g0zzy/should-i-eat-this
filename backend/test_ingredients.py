"""Live standalone smoke test for the ingredient-resolution stage.

Run from ``backend`` with ``python test_ingredients.py``. The script uses the
configured Tavily and LLM credentials and intentionally does not call evidence.py.
"""
from __future__ import annotations

import json
import re

from ingredients import filter_notable, resolve_ingredients

PRODUCT_NAMES = ("Snickers", "REWE Bio Hummus", "Coca-Cola")
NEUTRAL_TERMS = {"water", "wasser", "salt", "salz", "sea salt", "meersalz"}
NOTABLE_MARKERS = (
    "sugar",
    "zucker",
    "syrup",
    "sirup",
    "agave",
    "dicksaft",
    "sweetener",
    "süßungsmittel",
    "acid",
    "säuerungsmittel",
    "colour",
    "color",
    "farbstoff",
    "preservative",
    "konservierungsstoff",
    "palm",
    "oil",
    "öl",
)


def _is_neutral(item: str) -> bool:
    normalized = item.casefold().strip()
    return normalized in NEUTRAL_TERMS or normalized in {"carbonated water", "kohlensäurehaltiges wasser"}


def _looks_notable(item: str) -> bool:
    normalized = item.casefold()
    return any(marker in normalized for marker in NOTABLE_MARKERS) or bool(
        re.search(r"\be[ -]?\d{3,4}[a-z]?\b", normalized)
    )


def main() -> None:
    failures: list[str] = []

    for product_name in PRODUCT_NAMES:
        resolved = resolve_ingredients(product_name)
        notable = filter_notable(resolved["ingredients"])

        print(f"\n=== {product_name} ===")
        print(f"source_url: {resolved['source_url']}")
        print(f"source_type: {resolved['source_type']}")
        print(f"confidence: {resolved['confidence']}")
        print("raw ingredients:")
        print(json.dumps(resolved["ingredients"], ensure_ascii=False, indent=2))
        print("filtered notable ingredients:")
        print(json.dumps(notable, ensure_ascii=False, indent=2))

        if not resolved["ingredients"] or resolved["source_type"] != "web":
            failures.append(f"{product_name}: no live ingredient list was resolved")

        leaked_neutral = [item for item in notable if _is_neutral(item)]
        if leaked_neutral:
            failures.append(f"{product_name}: neutral items were retained: {leaked_neutral}")

        raw_notable = [item for item in resolved["ingredients"] if _looks_notable(item)]
        if raw_notable and not any(_looks_notable(item) for item in notable):
            failures.append(f"{product_name}: notable additives/sweeteners were not retained")

    if failures:
        raise SystemExit("\nIngredient smoke test failed:\n- " + "\n- ".join(failures))

    print("\nIngredient smoke test passed.")


if __name__ == "__main__":
    main()
