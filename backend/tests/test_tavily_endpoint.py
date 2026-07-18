import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app


class TavilyEndpointTests(unittest.TestCase):
    def test_resolve_and_evidence_uses_product_name_flow(self):
        resolved_product = {
            "name": "Snickers",
            "brand": "Snickers",
            "ingredients": ["peanuts", "sugar"],
            "nutrition": {
                "serving_size": "1 bar",
                "calories": 250,
                "total_sugar_g": 27,
                "added_sugar_g": 25,
                "fiber_g": 1,
                "protein_g": 5,
                "sodium_mg": 130,
                "total_fat_g": 12,
                "saturated_fat_g": 4.5,
                "trans_fat_g": 0,
                "cholesterol_mg": 10,
                "total_carbohydrate_g": 33,
                "vitamin_d_mcg": None,
                "calcium_mg": 60,
                "iron_mg": 0.8,
                "potassium_mg": 200,
                "additional_nutrients": {"caffeine_mg": 0},
            },
            "label_source_url": "https://www.snickers.com/example",
            "label_source_type": "manufacturer",
            "confidence": "high",
        }
        resolution = {"status": "resolved", "product": resolved_product}
        evidence = [
            {
                "topic": "added_sugar",
                "status": "found",
                "product_trigger": "25g added sugar per serving",
                "claim": "A concise cited claim.",
                "source_url": "https://www.cdc.gov/example",
                "source_title": "CDC example",
                "source_type": "public_health",
                "relevance": "high",
            }
        ]

        with patch("main.resolve_product", new=AsyncMock(return_value=resolution)) as resolve_mock:
            with patch("main.find_relevant_evidence", new=AsyncMock(return_value=evidence)) as evidence_mock:
                response = TestClient(app).post(
                    "/resolve-and-evidence",
                    json={"product_name": "Snickers", "persona_id": "diabetic"},
                )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["product_resolution"], resolution)
        self.assertEqual(body["evidence"], evidence)
        resolve_mock.assert_awaited_once_with("Snickers", include_debug=False)
        evidence_mock.assert_awaited_once()
        self.assertEqual(evidence_mock.await_args.args[0], resolved_product)
        self.assertIn("type_2_diabetes", evidence_mock.await_args.args[1]["health_conditions"])


if __name__ == "__main__":
    unittest.main()
