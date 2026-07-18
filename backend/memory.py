"""Persistent persona memory, backed by Cognee.

TODO(real-integration): replace the stub bodies below with real Cognee calls.
Cognee docs: https://docs.cognee.ai

Expected real flow:
  1. seed_personas() loads seed/personas.json and cognifies each persona's
     text profile into Cognee's knowledge graph / vector store, tagged by
     persona id, once at startup (or via a one-off setup script).
  2. get_context(persona_id) runs a Cognee `search`/`cognify` query scoped
     to that persona id and returns a short synthesized text blob describing
     everything relevant we "remember" about them (conditions, past
     reactions, preferences) for the synthesis step to use as grounding.
"""
import json
from pathlib import Path

SEED_DIR = Path(__file__).parent / "seed"


async def seed_personas() -> None:
    """Load persona profiles into Cognee's memory store.

    TODO(real-integration): call `cognee.add(...)` + `cognee.cognify()` for
    each persona in seed/personas.json so their profile text becomes queryable
    knowledge. For now this is a no-op stub — mock mode does not need it.
    """
    raise NotImplementedError("seed_personas() is a stub — wire up Cognee here")


async def get_context(persona_id: str) -> str:
    """Return a text blob of everything remembered about this persona.

    TODO(real-integration): call `cognee.search(query=..., persona_id=...)`
    (or equivalent) and condense the results into a short paragraph.

    Args:
        persona_id: id matching an entry in seed/personas.json

    Returns:
        A natural-language summary of relevant persona context.
    """
    raise NotImplementedError("get_context() is a stub — wire up Cognee here")


def load_persona_profiles() -> list[dict]:
    """Helper: read the raw seed file (used by mock mode and by seeding)."""
    with open(SEED_DIR / "personas.json") as f:
        return json.load(f)
