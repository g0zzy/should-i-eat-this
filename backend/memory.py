"""Backwards-compatible façade for the Cognee person-memory service.

New code should import typed models and functions from
``services.memory_service``.  The original ``seed_personas`` and
``get_context`` entry points remain available while the mock evaluator is
still in place.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from services.memory_service import (
    CogneeMemoryService,
    EvaluationContext,
    FoodDecisionEvent,
    PersonProfile,
)

SEED_DIR = Path(__file__).parent / "seed"
_service = CogneeMemoryService()


def load_persona_profiles() -> list[dict[str, Any]]:
    """Read the legacy persona seed file used by the current mock UI."""
    with open(SEED_DIR / "personas.json") as file:
        return json.load(file)


def _legacy_profile(persona: dict[str, Any]) -> PersonProfile:
    """Map the existing prose-only demo personas to the structured model."""
    if persona["id"] == "diabetic":
        return PersonProfile(
            persona_id="diabetic",
            name=persona["name"],
            health_conditions=["type_2_diabetes"],
            medications_or_considerations=["metformin"],
            dietary_goals=["limit_added_sugar", "increase_fiber"],
            personal_rules=[
                "Avoid snacks with more than 20g sugar per serving.",
                "Prefer snacks with at least 5g protein or fiber.",
                "Doctor-recommended added-sugar target is under 25g per day.",
            ],
        )
    return PersonProfile(
        persona_id="athlete",
        name=persona["name"],
        health_conditions=[],
        dietary_goals=["fuel_endurance_training", "avoid_pre_run_gi_distress"],
        personal_rules=[
            "Avoid high-fat, high-fiber foods within two hours of a run.",
            "Quick-digesting carbohydrates and electrolytes are appropriate around training.",
        ],
    )


async def seed_personas() -> None:
    """Seed/update the two structured demo profiles, without food history."""
    for persona in load_persona_profiles():
        await _service.upsert_profile(_legacy_profile(persona))


async def seed_demo_memory() -> None:
    """Seed profiles plus fictional food-decision history for the POC demo.

    This is safe to run for profiles. Food events are append-only, so run it
    once per empty demo tenant rather than repeatedly.
    """
    await seed_personas()
    with open(SEED_DIR / "demo_memory_events.json") as file:
        events = json.load(file)
    for event in events:
        await _service.record_food_decision(FoodDecisionEvent.model_validate(event))


async def get_evaluation_context(
    persona_id: str, product: dict[str, Any], now: datetime
) -> EvaluationContext:
    """Retrieve product-specific profile and food-decision memory."""
    return await _service.get_evaluation_context(persona_id, product, now)


async def get_context(persona_id: str) -> str:
    """Legacy generic context accessor retained for existing integrations."""
    context = await get_evaluation_context(
        persona_id,
        {"name": "a food product", "ingredients": [], "nutrition": {}},
        datetime.now().astimezone(),
    )
    return context.context_text
