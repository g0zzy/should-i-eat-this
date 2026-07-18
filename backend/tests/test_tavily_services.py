import unittest

from services.evidence_service import EvidenceSearchError, find_relevant_evidence
from services.product_resolver import ProductResolutionError, resolve_product


class FakeTavilyClient:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.responses.pop(0)


class ProductResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_product_page_resolves_successfully(self):
        client = FakeTavilyClient(
            [
                {
                    "results": [
                        {
                            "title": "Nature Valley Oats & Honey Granola Bars",
                            "url": "https://www.naturevalley.com/products/oats-honey",
                            "content": (
                                "Nature Valley Oats & Honey Granola Bars. "
                                "Ingredients: whole grain oats, sugar, canola oil, honey, "
                                "brown sugar syrup, salt, baking soda, soy lecithin. "
                                "Nutrition Facts. Serving Size 2 bars (42g). Calories 190. "
                                "Total Fat 7g. Saturated Fat 1g. Trans Fat 0g. "
                                "Cholesterol 0mg. Sodium 160mg. Total Carbohydrate 29g. "
                                "Total Sugars 11g. Added Sugars 11g. Fiber 2g. "
                                "Protein 3g. Calcium 20mg. Iron 1.2mg. Potassium 80mg. "
                                "Sugar Alcohol 2g. Caffeine 35mg."
                            ),
                        }
                    ]
                }
            ]
        )

        resolution = await resolve_product("Nature Valley Oats & Honey Granola Bar", client=client)

        self.assertEqual(resolution["status"], "resolved")
        product = resolution["product"]
        self.assertEqual(product["label_source_type"], "manufacturer")
        self.assertEqual(product["confidence"], "high")
        self.assertEqual(product["ingredients"][0], "whole grain oats")
        self.assertEqual(product["nutrition"]["added_sugar_g"], 11)
        self.assertEqual(product["nutrition"]["saturated_fat_g"], 1)
        self.assertEqual(product["nutrition"]["total_carbohydrate_g"], 29)
        self.assertEqual(product["nutrition"]["potassium_mg"], 80)
        self.assertEqual(product["nutrition"]["additional_nutrients"]["sugar_alcohol_g"], 2)
        self.assertEqual(product["nutrition"]["additional_nutrients"]["caffeine_mg"], 35)

    async def test_ambiguous_search_returns_needs_confirmation(self):
        client = FakeTavilyClient(
            [
                {
                    "results": [
                        {
                            "title": "Snickers Ice Cream Bar Nutrition",
                            "url": "https://www.walmart.com/ip/snickers-ice-cream",
                            "content": "Snickers Ice Cream Bar ingredients and nutrition facts.",
                        },
                        {
                            "title": "Snickers Almond Bar Nutrition",
                            "url": "https://www.target.com/p/snickers-almond",
                            "content": "Snickers Almond Bar ingredients and nutrition facts.",
                        },
                    ]
                }
            ]
        )

        resolution = await resolve_product("Snickers", client=client)

        self.assertEqual(resolution["status"], "needs_confirmation")
        self.assertGreaterEqual(len(resolution["candidates"]), 1)

    async def test_missing_nutrition_label_is_not_invented(self):
        client = FakeTavilyClient(
            [
                {
                    "results": [
                        {
                            "title": "Oreo Cookies",
                            "url": "https://www.oreo.com/product/original",
                            "content": "Oreo Cookies. Ingredients: sugar, flour, palm oil, cocoa, soy lecithin.",
                        }
                    ]
                }
            ]
        )

        resolution = await resolve_product("Oreo Cookies", client=client)

        self.assertEqual(resolution["status"], "needs_confirmation")
        self.assertNotIn("product", resolution)

    async def test_product_tavily_failure_returns_safe_error(self):
        client = FakeTavilyClient(error=RuntimeError("secret low-level failure"))

        with self.assertRaises(ProductResolutionError) as raised:
            await resolve_product("Any Product", client=client)

        self.assertEqual(str(raised.exception), "Product lookup failed. Try again later.")


class EvidenceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_diabetic_high_added_sugar_searches_added_sugar_topic(self):
        product = {
            "ingredients": ["whole grain oats", "sugar"],
            "nutrition": {"added_sugar_g": 11, "total_sugar_g": 11},
        }
        profile = {
            "health_conditions": ["type_2_diabetes"],
            "allergies_or_intolerances": [],
            "dietary_goals": ["limit_added_sugar"],
            "personal_rules": [],
        }
        client = FakeTavilyClient(
            [
                {
                    "results": [
                        {
                            "title": "Added Sugars and Diabetes",
                            "url": "https://diabetes.org/food-nutrition/reading-food-labels/added-sugars",
                            "content": "Diabetes guidance discusses added sugars and blood sugar management.",
                        }
                    ]
                }
            ]
        )

        evidence = await find_relevant_evidence(product, profile, client=client)

        self.assertEqual(client.calls[0]["query"], "added sugar type 2 diabetes clinical guideline")
        self.assertEqual(evidence[0]["topic"], "added_sugar")
        self.assertEqual(evidence[0]["source_type"], "professional_association")

    async def test_ordinary_non_relevant_ingredients_do_not_search(self):
        product = {
            "ingredients": ["water", "whole grain oats"],
            "nutrition": {"added_sugar_g": 0, "fiber_g": 4, "protein_g": 6},
        }
        profile = {
            "health_conditions": [],
            "allergies_or_intolerances": [],
            "dietary_goals": [],
            "personal_rules": [],
        }
        client = FakeTavilyClient([])

        evidence = await find_relevant_evidence(product, profile, client=client)

        self.assertEqual(evidence, [])
        self.assertEqual(client.calls, [])

    async def test_evidence_tavily_failure_returns_safe_error(self):
        product = {"ingredients": ["sugar"], "nutrition": {"added_sugar_g": 20}}
        profile = {"health_conditions": ["type_2_diabetes"], "dietary_goals": ["limit_added_sugar"]}
        client = FakeTavilyClient(error=RuntimeError("raw timeout with details"))

        with self.assertRaises(EvidenceSearchError) as raised:
            await find_relevant_evidence(product, profile, client=client)

        self.assertEqual(str(raised.exception), "Evidence lookup failed. Try again later.")

    async def test_low_quality_evidence_domains_are_returned_as_gap(self):
        product = {
            "ingredients": ["sugar"],
            "nutrition": {"added_sugar_g": 18, "total_sugar_g": 18},
        }
        profile = {"health_conditions": ["type_2_diabetes"], "dietary_goals": ["limit_added_sugar"]}
        client = FakeTavilyClient(
            [
                {
                    "results": [
                        {
                            "title": "A Blog About Sugar",
                            "url": "https://example-blog.test/sugar-is-scary",
                            "content": "A low-quality health claim about sugar.",
                        }
                    ]
                }
            ]
        )

        evidence = await find_relevant_evidence(product, profile, client=client, include_debug=True)

        self.assertEqual(evidence[0]["status"], "no_high_quality_source_found")
        self.assertEqual(evidence[0]["topic"], "added_sugar")
        self.assertIn("debug", evidence[0])
        self.assertEqual(evidence[0]["debug"]["decisions"][0]["selected"], False)


if __name__ == "__main__":
    unittest.main()
