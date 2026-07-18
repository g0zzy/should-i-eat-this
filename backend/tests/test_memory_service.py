import unittest
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from services.memory_service import (
    CogneeMemoryService,
    FoodDecisionEvent,
    PersonProfile,
    ProductSnapshot,
    Nutrition,
    dataset_name_for,
)


class FakeCogneeClient:
    def __init__(self):
        self.datasets = {}
        self.documents = {}
        self.search_results = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def list_datasets(self):
        return list(self.datasets.values())

    async def create_dataset(self, name):
        dataset = SimpleNamespace(id=uuid4(), name=name)
        self.datasets[name] = dataset
        self.documents[dataset.id] = {}
        return dataset

    async def get_dataset_data(self, dataset_id):
        return [SimpleNamespace(id=data_id) for data_id in self.documents[dataset_id]]

    async def download_raw_data(self, dataset_id, data_id):
        return self.documents[dataset_id][data_id].encode()

    async def add(self, data, dataset_name):
        dataset = self.datasets[dataset_name]
        data_id = uuid4()
        self.documents[dataset.id][data_id] = data
        return SimpleNamespace(data_id=data_id)

    async def update(self, data_id, dataset_id, data):
        self.documents[dataset_id][data_id] = data

    async def delete(self, data_id, dataset_id):
        del self.documents[dataset_id][data_id]

    async def cognify(self, datasets):
        return {name: {"status": "completed"} for name in datasets}

    async def search(self, **kwargs):
        return self.search_results


class MemoryServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = FakeCogneeClient()
        self.service = CogneeMemoryService(client_factory=lambda: self.client)
        self.maria = PersonProfile(
            persona_id="maria",
            name="Maria",
            health_conditions=["type_2_diabetes"],
            dietary_goals=["limit_added_sugar"],
            personal_rules=["Avoid high-sugar snacks."],
        )

    async def test_profile_upsert_updates_in_place(self):
        await self.service.upsert_profile(self.maria)
        updated = self.maria.model_copy(update={"personal_rules": ["Choose high-fiber snacks."]})
        await self.service.upsert_profile(updated)

        dataset = self.client.datasets[dataset_name_for("maria")]
        self.assertEqual(len(self.client.documents[dataset.id]), 1)
        raw = next(iter(self.client.documents[dataset.id].values()))
        self.assertIn("Choose high-fiber snacks.", raw)
        self.assertNotIn("Avoid high-sugar snacks.", raw)

    async def test_persona_datasets_are_isolated(self):
        await self.service.upsert_profile(self.maria)
        jordan = PersonProfile(persona_id="jordan", name="Jordan", dietary_goals=["fuel_running"])
        await self.service.upsert_profile(jordan)
        self.assertNotEqual(dataset_name_for("maria"), dataset_name_for("jordan"))
        self.assertEqual(len(self.client.datasets), 2)

    async def test_relevant_event_is_returned_with_timestamp(self):
        await self.service.upsert_profile(self.maria)
        event = FoodDecisionEvent(
            event_id="maria-bar",
            persona_id="maria",
            occurred_at=datetime.fromisoformat("2026-07-14T15:30:00+02:00"),
            product=ProductSnapshot(
                name="Sugary snack bar",
                ingredients=["sugar"],
                nutrition=Nutrition(added_sugar_g=22, fiber_g=1),
            ),
            recommendation="avoid",
            ate_it=True,
            outcome="energy_crash",
        )
        await self.service.record_food_decision(event)
        dataset = self.client.datasets[dataset_name_for("maria")]
        event_raw = [raw for raw in self.client.documents[dataset.id].values() if "maria-bar" in raw][0]
        # Cloud SDK 0.3.0 nests the chunk text under search_result rather than
        # populating top-level SearchResult.text.
        self.client.search_results = [
            SimpleNamespace(text=None, search_result=[{"text": event_raw}])
        ]

        context = await self.service.get_evaluation_context(
            "maria", {"name": "Granola bar", "ingredients": ["sugar"], "nutrition": {"added_sugar_g": 11}}, datetime.now().astimezone()
        )
        self.assertEqual(context.retrieval_status, "ok")
        self.assertEqual(context.relevant_memories[0].occurred_at, event.occurred_at)
        self.assertIn("energy_crash", context.relevant_memories[0].summary)

    async def test_no_history_returns_profile_only(self):
        await self.service.upsert_profile(self.maria)
        self.client.search_results = []
        context = await self.service.get_evaluation_context(
            "maria", {"name": "Unknown food", "ingredients": [], "nutrition": {}}, datetime.now().astimezone()
        )
        self.assertEqual(context.retrieval_status, "empty")
        self.assertEqual(context.profile.persona_id, "maria")
        self.assertEqual(context.relevant_memories, [])

    async def test_unconfigured_service_is_safe_for_retrieval(self):
        service = CogneeMemoryService(api_url="", api_key="")
        context = await service.get_evaluation_context("maria", {}, datetime.now().astimezone())
        self.assertEqual(context.retrieval_status, "unavailable")
        self.assertIsNone(context.profile)


if __name__ == "__main__":
    unittest.main()
