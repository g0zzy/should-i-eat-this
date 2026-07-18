"""Cognee Cloud-backed, person-scoped memory for food decisions.

Cognee is used as retrieval memory, not the application's only record of
health data.  The service stores structured records as readable JSON documents
so their identifiers and dates are part of the indexed content.  Callers should
also keep their source-of-truth profile/event records in their own database when
one is introduced.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any, Callable, Literal

from cognee_sdk import CogneeClient
from cognee_sdk.models import SearchType
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv()

RECORD_PREFIX = "SHOULD_I_EAT_THIS_MEMORY_RECORD\n"
PROFILE_RECORD_TYPE = "person_profile"


class MemoryConfigurationError(RuntimeError):
    """Raised when Cognee Cloud credentials have not been configured."""


class MemoryUnavailableError(RuntimeError):
    """Raised when a configured Cognee Cloud service cannot be reached."""


class Nutrition(BaseModel):
    added_sugar_g: float | None = None
    fiber_g: float | None = None
    protein_g: float | None = None
    sodium_mg: float | None = None


class ProductSnapshot(BaseModel):
    name: str
    brand: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    nutrition: Nutrition = Field(default_factory=Nutrition)


class PersonProfile(BaseModel):
    persona_id: str
    name: str
    health_conditions: list[str] = Field(default_factory=list)
    allergies_or_intolerances: list[str] = Field(default_factory=list)
    medications_or_considerations: list[str] = Field(default_factory=list)
    dietary_goals: list[str] = Field(default_factory=list)
    personal_rules: list[str] = Field(default_factory=list)


class FoodDecisionEvent(BaseModel):
    event_id: str
    persona_id: str
    occurred_at: datetime
    type: Literal["food_decision"] = "food_decision"
    product: ProductSnapshot
    recommendation: Literal["eat", "moderate", "avoid"]
    ate_it: bool | None = None
    outcome: Literal["energy_crash", "fine", "symptoms", "unknown"] = "unknown"
    notes: str | None = None


class RelevantMemory(BaseModel):
    type: Literal["prior_food_decision", "reported_outcome", "preference"]
    summary: str
    occurred_at: datetime | None = None
    relevance_reason: str


class EvaluationContext(BaseModel):
    profile: PersonProfile | None = None
    relevant_memories: list[RelevantMemory] = Field(default_factory=list)
    context_text: str = ""
    retrieval_status: Literal["ok", "empty", "unavailable"]


def dataset_name_for(persona_id: str) -> str:
    """Return a stable, opaque dataset name without exposing a user identifier."""
    digest = hashlib.sha256(persona_id.encode("utf-8")).hexdigest()[:20]
    return f"persona-{digest}"


def _record_document(record_type: str, payload: dict[str, Any], summary: str) -> str:
    """Make records both machine-readable and meaningful to Cognee retrieval."""
    return RECORD_PREFIX + json.dumps(
        {"memory_record_type": record_type, "summary": summary, **payload},
        default=str,
        sort_keys=True,
    )


def _profile_document(profile: PersonProfile) -> str:
    summary = (
        f"Profile for {profile.name}. Conditions: {', '.join(profile.health_conditions) or 'none recorded'}. "
        f"Allergies or intolerances: {', '.join(profile.allergies_or_intolerances) or 'none recorded'}. "
        f"Goals: {', '.join(profile.dietary_goals) or 'none recorded'}. "
        f"Personal rules: {'; '.join(profile.personal_rules) or 'none recorded'}."
    )
    return _record_document(PROFILE_RECORD_TYPE, profile.model_dump(mode="json"), summary)


def _event_document(event: FoodDecisionEvent) -> str:
    nutrition = event.product.nutrition
    nutrients = ", ".join(
        f"{label} {value:g}{unit}"
        for label, value, unit in (
            ("added sugar", nutrition.added_sugar_g, "g"),
            ("fiber", nutrition.fiber_g, "g"),
            ("protein", nutrition.protein_g, "g"),
            ("sodium", nutrition.sodium_mg, "mg"),
        )
        if value is not None
    ) or "nutrition not recorded"
    ate = "ate it" if event.ate_it else "did not eat it" if event.ate_it is False else "did not report whether they ate it"
    summary = (
        f"On {event.occurred_at.isoformat()}, this person considered {event.product.name}, "
        f"was advised to {event.recommendation}, {ate}, and reported outcome: {event.outcome}. "
        f"Product details: ingredients {', '.join(event.product.ingredients) or 'not recorded'}; {nutrients}."
    )
    if event.notes:
        summary += f" User note: {event.notes}"
    return _record_document("food_decision", event.model_dump(mode="json"), summary)


class CogneeMemoryService:
    """A small adapter around the async Cognee Cloud SDK.

    Profile updates locate the existing structured profile record in the
    persona dataset and update it in place. Duplicate legacy profile records
    are removed. Food-decision events are immutable append-only records.
    """

    def __init__(
        self,
        client_factory: Callable[[], CogneeClient] | None = None,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.api_url = api_url if api_url is not None else os.getenv("COGNEE_API_URL")
        self.api_key = api_key if api_key is not None else os.getenv("COGNEE_API_KEY")
        self._client_factory = client_factory
        self.last_index_result: dict[str, Any] | None = None
        self._profile_cache: dict[str, PersonProfile] = {}

    def _client(self) -> CogneeClient:
        if self._client_factory:
            return self._client_factory()
        if not self.api_url or not self.api_key:
            raise MemoryConfigurationError(
                "Cognee memory requires COGNEE_API_URL and COGNEE_API_KEY in backend/.env"
            )
        # Cognee Cloud API keys use X-Api-Key. The lightweight cognee-sdk
        # defaults to a Bearer Authorization header, but exposes this hook for
        # Cloud-compatible authentication without replacing the SDK.
        def cloud_api_key_auth(_method: str, _url: str, headers: dict[str, str]) -> None:
            headers.pop("Authorization", None)
            headers["X-Api-Key"] = self.api_key

        return CogneeClient(
            api_url=self.api_url,
            request_interceptor=cloud_api_key_auth,
        )

    async def _dataset(self, client: CogneeClient, persona_id: str) -> Any:
        name = dataset_name_for(persona_id)
        datasets = await client.list_datasets()
        existing = next((dataset for dataset in datasets if dataset.name == name), None)
        return existing or await client.create_dataset(name)

    async def _existing_dataset(self, client: CogneeClient, persona_id: str) -> Any | None:
        name = dataset_name_for(persona_id)
        return next((dataset for dataset in await client.list_datasets() if dataset.name == name), None)

    async def _profile_records(self, client: CogneeClient, dataset: Any) -> list[Any]:
        records = []
        for item in await client.get_dataset_data(dataset.id):
            try:
                raw = (await client.download_raw_data(dataset.id, item.id)).decode("utf-8")
                if raw.startswith(RECORD_PREFIX) and json.loads(raw[len(RECORD_PREFIX):]).get("memory_record_type") == PROFILE_RECORD_TYPE:
                    records.append((item, raw))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return records

    @staticmethod
    async def _update_profile_record(client: CogneeClient, data_id: Any, dataset_id: Any, document: str) -> None:
        """Update a profile while tolerating a cognee-sdk 0.3.0 response bug.

        Cognee Cloud returns a successful PATCH response keyed by pipeline run,
        whereas this SDK version attempts to parse it as ``UpdateResult`` with
        required ``status`` and ``message`` fields. The request has already
        succeeded when that Pydantic ValidationError is raised.
        """
        try:
            await client.update(data_id, dataset_id, document)
        except ValidationError as exc:
            errors = exc.errors()
            missing = {error.get("loc", (None,))[0] for error in errors if error.get("type") == "missing"}
            if missing != {"status", "message"}:
                raise

    async def upsert_profile(self, profile: PersonProfile) -> None:
        document = _profile_document(profile)
        try:
            async with self._client() as client:
                dataset = await self._dataset(client, profile.persona_id)
                records = await self._profile_records(client, dataset)
                if records:
                    await self._update_profile_record(client, records[0][0].id, dataset.id, document)
                    for duplicate, _ in records[1:]:
                        await client.delete(duplicate.id, dataset.id)
                else:
                    await client.add(data=document, dataset_name=dataset.name)
                self.last_index_result = await client.cognify(datasets=[dataset.name])
                self._profile_cache[profile.persona_id] = profile
        except MemoryConfigurationError:
            raise
        except Exception as exc:
            raise MemoryUnavailableError("Cognee Cloud could not save this profile") from exc

    async def record_food_decision(self, event: FoodDecisionEvent) -> None:
        try:
            async with self._client() as client:
                dataset = await self._dataset(client, event.persona_id)
                # event_id is indexed in the document. Callers should not submit it twice.
                await client.add(data=_event_document(event), dataset_name=dataset.name)
                self.last_index_result = await client.cognify(datasets=[dataset.name])
        except MemoryConfigurationError:
            raise
        except Exception as exc:
            raise MemoryUnavailableError("Cognee Cloud could not save this food decision") from exc

    async def _load_profile(self, client: CogneeClient, dataset: Any) -> PersonProfile | None:
        records = await self._profile_records(client, dataset)
        if not records:
            return None
        payload = json.loads(records[0][1][len(RECORD_PREFIX):])
        return PersonProfile.model_validate(payload)

    @staticmethod
    def _query_for(product: dict[str, Any], now: datetime) -> str:
        nutrition = product.get("nutrition") or {}
        ingredients = ", ".join(product.get("ingredients") or [])
        triggers = ", ".join(
            f"{key}={value}" for key, value in nutrition.items()
            if key in {"added_sugar_g", "fiber_g", "protein_g", "sodium_mg"} and value is not None
        ) or "no nutrition triggers supplied"
        return (
            "Return only prior food-decision records or reported outcomes relevant to evaluating this product. "
            f"Product: {product.get('name', 'unknown')}. Ingredients: {ingredients or 'unknown'}. "
            f"Nutrition triggers: {triggers}. Current time: {now.isoformat()}. "
            "Prioritize ingredient matches, similar sugar/fiber/protein/sodium profiles, and reported outcomes. "
            "Include dates and do not include the stable profile record."
        )

    @staticmethod
    def _memory_from_result(text: str) -> RelevantMemory | None:
        if PROFILE_RECORD_TYPE in text:
            return None
        occurred_match = re.search(r'"occurred_at"\s*:\s*"([^"]+)"', text)
        occurred_at = None
        if occurred_match:
            try:
                occurred_at = datetime.fromisoformat(occurred_match.group(1))
            except ValueError:
                pass
        outcome = "reported outcome" if '"outcome"' in text else "prior food decision"
        return RelevantMemory(
            type="reported_outcome" if outcome == "reported outcome" else "prior_food_decision",
            summary=text.strip()[:1000],
            occurred_at=occurred_at,
            relevance_reason="Cognee matched this prior decision to the product ingredients or nutrition profile.",
        )

    @staticmethod
    def _texts_from_search_result(result: Any) -> list[str]:
        """Normalize both documented and current Cloud SDK result shapes.

        cognee-sdk 0.3.0 returns Cloud chunk payloads in ``search_result``
        while leaving the top-level ``SearchResult.text`` empty.
        """
        if isinstance(result, dict):
            direct_text = result.get("text")
            nested = result.get("search_result") or []
        else:
            direct_text = getattr(result, "text", None)
            nested = getattr(result, "search_result", None) or []
        texts = [direct_text] if isinstance(direct_text, str) and direct_text else []
        for item in nested:
            text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            if isinstance(text, str) and text:
                texts.append(text)
        return texts

    @staticmethod
    def _context_text(profile: PersonProfile | None, memories: list[RelevantMemory]) -> str:
        parts: list[str] = []
        if profile:
            parts.append(
                "Known profile: "
                + "; ".join(filter(None, [
                    f"conditions: {', '.join(profile.health_conditions)}" if profile.health_conditions else "",
                    f"allergies/intolerances: {', '.join(profile.allergies_or_intolerances)}" if profile.allergies_or_intolerances else "",
                    f"goals: {', '.join(profile.dietary_goals)}" if profile.dietary_goals else "",
                    f"personal rules: {'; '.join(profile.personal_rules)}" if profile.personal_rules else "",
                ]))
            )
        if memories:
            parts.append("Relevant reported history: " + " | ".join(memory.summary for memory in memories))
        return "\n".join(parts)

    async def get_evaluation_context(
        self,
        persona_id: str,
        product: dict[str, Any],
        now: datetime,
        *,
        fallback_profile: PersonProfile | None = None,
    ) -> EvaluationContext:
        try:
            async with self._client() as client:
                dataset = await self._existing_dataset(client, persona_id)
                if dataset is None:
                    profile = fallback_profile or self._profile_cache.get(persona_id)
                    return EvaluationContext(
                        profile=profile,
                        context_text=self._context_text(profile, []),
                        retrieval_status="empty",
                    )
                profile = await self._load_profile(client, dataset) or fallback_profile or self._profile_cache.get(persona_id)
                results = await client.search(
                    query=self._query_for(product, now),
                    search_type=SearchType.CHUNKS,
                    datasets=[dataset.name],
                    top_k=5,
                )
        except MemoryConfigurationError:
            profile = fallback_profile or self._profile_cache.get(persona_id)
            return EvaluationContext(
                profile=profile,
                context_text=self._context_text(profile, []),
                retrieval_status="unavailable",
            )
        except Exception:
            profile = fallback_profile or self._profile_cache.get(persona_id)
            return EvaluationContext(
                profile=profile,
                context_text=self._context_text(profile, []),
                retrieval_status="unavailable",
            )

        memories = []
        seen: set[str] = set()
        for result in results:
            for text in self._texts_from_search_result(result):
                if text in seen:
                    continue
                seen.add(text)
                memory = self._memory_from_result(text)
                if memory:
                    memories.append(memory)
        status: Literal["ok", "empty"] = "ok" if memories else "empty"
        return EvaluationContext(
            profile=profile,
            relevant_memories=memories,
            context_text=self._context_text(profile, memories),
            retrieval_status=status,
        )


# Module-level helpers provide the small public API used by application code.
# Tests and advanced callers can instantiate CogneeMemoryService with a fake
# client factory instead.
_default_service = CogneeMemoryService()


async def upsert_profile(profile: PersonProfile) -> None:
    await _default_service.upsert_profile(profile)


async def record_food_decision(event: FoodDecisionEvent) -> None:
    await _default_service.record_food_decision(event)


async def get_evaluation_context(
    persona_id: str,
    product: dict[str, Any],
    now: datetime,
    *,
    fallback_profile: PersonProfile | None = None,
) -> EvaluationContext:
    return await _default_service.get_evaluation_context(
        persona_id, product, now, fallback_profile=fallback_profile
    )
