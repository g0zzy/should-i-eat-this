"""Persistent persona memory, backed by Cognee Cloud.

Uses the lightweight `cognee-sdk` client (a thin httpx wrapper over the
Cognee Cloud REST API) rather than the full `cognee` package — that avoids
pulling in cognee's local vector/graph DB stack and its Rust-built
`cbor2` dependency, which isn't needed when Cognee is doing the hosting.

Each persona gets its own Cognee dataset (dataset_name == persona_id), so
get_context() can scope its search to just that person's data.
"""
import json
import os
from pathlib import Path

from cognee_sdk import CogneeClient
from cognee_sdk.models import SearchType
from dotenv import load_dotenv

load_dotenv()

SEED_DIR = Path(__file__).parent / "seed"

COGNEE_API_URL = os.environ["COGNEE_API_URL"]
COGNEE_API_KEY = os.environ["COGNEE_API_KEY"]


def load_persona_profiles() -> list[dict]:
    """Read the raw seed file (used by seed_personas() and by mock mode)."""
    with open(SEED_DIR / "personas.json") as f:
        return json.load(f)


def _client() -> CogneeClient:
    return CogneeClient(api_url=COGNEE_API_URL, api_token=COGNEE_API_KEY)


async def seed_personas() -> None:
    """Load each persona's profile text into its own Cognee dataset and
    run cognify so it becomes queryable knowledge. Run this once at startup
    (or via a one-off setup script) before calling get_context().
    """
    personas = load_persona_profiles()
    async with _client() as client:
        for persona in personas:
            await client.add(data=persona["profile"], dataset_name=persona["id"])
        await client.cognify(datasets=[p["id"] for p in personas])


async def get_context(persona_id: str) -> str:
    """Return a text blob of everything remembered about this persona.

    Args:
        persona_id: id matching an entry in seed/personas.json, and the
            Cognee dataset name it was seeded under.

    Returns:
        A natural-language summary of relevant persona context, synthesized
        by Cognee's graph-completion search over that persona's dataset.
    """
    async with _client() as client:
        results = await client.search(
            query=(
                "Summarize this person's health conditions, dietary needs, "
                "food preferences, and any past reactions to specific foods."
            ),
            search_type=SearchType.GRAPH_COMPLETION,
            datasets=[persona_id],
        )
    return "\n".join(r.text for r in results if r.text)
