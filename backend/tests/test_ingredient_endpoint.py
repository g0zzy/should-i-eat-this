import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class IngredientEndpointTests(unittest.TestCase):
    def test_resolve_ingredients_returns_raw_and_filtered_lists(self):
        resolution = {
            "product_name": "Snickers",
            "ingredients": ["Water", "Sugar", "Palm oil"],
            "source_url": "https://world.openfoodfacts.org/product/123/snickers",
            "source_type": "web",
            "confidence": "high",
        }

        with patch("main.resolve_ingredients", return_value=resolution) as resolve_mock:
            with patch("main.filter_notable", return_value=["sugar", "palm oil"]) as filter_mock:
                response = TestClient(app).post(
                    "/resolve-ingredients",
                    json={"product_name": "  Snickers  "},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {**resolution, "notable_ingredients": ["sugar", "palm oil"]},
        )
        resolve_mock.assert_called_once_with("Snickers")
        filter_mock.assert_called_once_with(resolution["ingredients"])

    def test_resolve_ingredients_rejects_blank_product_name(self):
        response = TestClient(app).post(
            "/resolve-ingredients",
            json={"product_name": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "product_name must not be empty")


if __name__ == "__main__":
    unittest.main()
