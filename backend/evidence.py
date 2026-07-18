"""Live web evidence lookup, backed by Tavily.

TODO(real-integration): replace the stub body below with a real Tavily
search. Tavily docs: https://docs.tavily.com
"""
import os

from tavily import TavilyClient


async def get_evidence(ingredients: list[str]) -> list[dict]:
    """Search the web for evidence about the given ingredients.

    TODO(real-integration):
      1. Instantiate `TavilyClient(api_key=os.environ["TAVILY_API_KEY"])`.
      2. For each ingredient (or a batched query), call `client.search(...)`
         with a health/nutrition-focused query, e.g.
         f"{ingredient} health effects nutrition research".
      3. Map results into dicts shaped like:
         {"claim": <short extracted claim text>, "source_url": <result url>}
      4. Return the flattened list across all ingredients.

    Args:
        ingredients: list of ingredient name strings from a product.

    Returns:
        A list of {"claim": str, "source_url": str} evidence dicts.
    """
    raise NotImplementedError("get_evidence() is a stub — wire up Tavily here")
