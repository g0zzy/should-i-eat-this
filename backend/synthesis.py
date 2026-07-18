"""LLM synthesis step: turns (product, persona context, evidence) into a
Verdict matching schema.EvaluateResponse.

TODO(real-integration): replace the stub body below with a real LLM call.

Config switch: set LLM_PROVIDER=anthropic or LLM_PROVIDER=openai in .env.
Both SDKs are lightweight to call directly — pick one code path at runtime
based on the env var so swapping providers doesn't require touching the
call site in main.py.
"""
import os

from schema import EvaluateResponse

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")  # "anthropic" | "openai"

SYSTEM_PROMPT = """You are a nutrition assistant that gives a personalized \
verdict on whether a specific person should eat a specific food product. \
Ground every flagged concern in the provided web evidence (cite source URLs) \
and in the person's known context. Respond ONLY with JSON matching this \
schema: {verdict: eat|moderate|avoid, headline, reasoning, flagged: \
[{item, concern, evidence: [{claim, source_url}]}], \
personal_context_used: [str], history_note, swap}."""


async def synthesize(
    product: dict, context: str, evidence: list[dict]
) -> EvaluateResponse:
    """Call an LLM to produce a personalized verdict.

    TODO(real-integration):
      1. Build a user prompt combining `product` (name/ingredients/nutrition),
         `context` (from memory.get_context), and `evidence` (from
         evidence.get_evidence).
      2. If LLM_PROVIDER == "anthropic": use `anthropic.Anthropic().messages.create(...)`
         with SYSTEM_PROMPT, requesting a JSON response.
         If LLM_PROVIDER == "openai": use `openai.OpenAI().chat.completions.create(...)`
         with response_format={"type": "json_object"}.
      3. Parse the JSON reply into an EvaluateResponse (pydantic will
         validate field names/types against the frozen contract).

    Args:
        product: a product dict (id, name, ingredients, nutrition).
        context: persona context string from memory.get_context().
        evidence: list of {"claim", "source_url"} dicts from evidence.get_evidence().

    Returns:
        A validated EvaluateResponse.
    """
    raise NotImplementedError("synthesize() is a stub — wire up an LLM call here")
