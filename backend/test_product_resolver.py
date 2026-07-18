"""Standalone verifier for Tavily-backed product ingredient resolution.

Usage:
  python backend/test_product_resolver.py "Snickers" "Oreo Biscuit"

The script loads TAVILY_API_KEY from backend/.env through product_resolver.py
and prints the normalized product label facts returned by Tavily-backed lookup.
"""
import asyncio
import json
import sys

from services.product_resolver import resolve_product


async def main() -> int:
    product_names = sys.argv[1:] or ["Snickers", "Oreo", "Coca Cola"]

    for product_name in product_names:
        print(f"\n=== {product_name} ===")
        resolution = await resolve_product(product_name, include_debug=True)
        print(json.dumps(resolution, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
