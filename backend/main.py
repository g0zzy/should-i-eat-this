"""FastAPI app for should-i-eat-this.

CRITICAL BUILD ORDER NOTE: /evaluate currently returns fully hardcoded MOCK
responses (see MOCK_RESPONSES below) so the frontend has something real to
render before the Cognee/Tavily/LLM integrations are wired up. Swap the body
of `evaluate()` for the real pipeline (memory.get_context -> evidence.get_evidence
-> synthesis.synthesize) once those stubs are implemented.
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from schema import EvaluateRequest, EvaluateResponse

SEED_DIR = Path(__file__).parent / "seed"

app = FastAPI(title="should-i-eat-this")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_seed(filename: str) -> list[dict]:
    with open(SEED_DIR / filename) as f:
        return json.load(f)


PRODUCTS = {p["id"]: p for p in _load_seed("products.json")}
PERSONAS = {p["id"]: p for p in _load_seed("personas.json")}


# ---------------------------------------------------------------------------
# MOCK DATA — hardcoded verdicts keyed by (product_id, persona_id).
# The granola-bar entries are the core demo: same product, opposite verdicts
# depending on which persona is selected.
# ---------------------------------------------------------------------------
MOCK_RESPONSES: dict[tuple[str, str], dict] = {
    ("granola-bar", "diabetic"): {
        "verdict": "avoid",
        "headline": "This bar will spike your blood sugar, Maria.",
        "reasoning": (
            "Nature Valley Oats & Honey packs 11g of sugar (all of it added) "
            "into a 42g serving with only 2g of fiber and 3g of protein to "
            "slow absorption. For someone managing Type 2 diabetes, that "
            "combination of refined sweeteners and low fiber is exactly the "
            "profile linked to rapid post-meal glucose spikes."
        ),
        "flagged": [
            {
                "item": "sugar, honey, brown sugar syrup",
                "concern": "Three separate added-sugar sources with minimal fiber to buffer absorption.",
                "evidence": [
                    {
                        "claim": "Refined carbohydrate snacks with low fiber content are associated with sharper post-prandial glucose excursions in people with type 2 diabetes.",
                        "source_url": "https://www.diabetes.org/food-nutrition/reading-food-labels/added-sugars",
                    },
                    {
                        "claim": "Granola bars are frequently high in added sugar despite a 'health food' image.",
                        "source_url": "https://www.health.harvard.edu/staying-healthy/are-granola-bars-a-healthy-snack",
                    },
                ],
            }
        ],
        "personal_context_used": [
            "Type 2 diabetes, manages blood sugar with metformin and diet",
            "Doctor-recommended cap of 25g added sugar/day",
            "History of energy crashes after >20g sugar servings",
        ],
        "history_note": "You've flagged energy crashes after similar high-sugar snacks before — this fits that pattern.",
        "swap": "Try a handful of unsalted almonds with a piece of string cheese — similar convenience, ~2g sugar, 13g protein.",
    },
    ("granola-bar", "athlete"): {
        "verdict": "eat",
        "headline": "Solid pre-run fuel, Jordan.",
        "reasoning": (
            "190 calories with 11g of quick-digesting sugar and 34g of total "
            "carbs is a reasonable pre-run or mid-long-run snack — the low "
            "fiber (2g) is actually a plus here since it won't sit heavy "
            "before a workout, and the oats provide a bit of sustained "
            "release alongside the fast sugars."
        ),
        "flagged": [
            {
                "item": "sugar, honey, brown sugar syrup",
                "concern": "High glycemic load — fine pre-run, but not an all-day snack.",
                "evidence": [
                    {
                        "claim": "Fast-digesting carbohydrates consumed 30-60 minutes before endurance exercise can top off glycogen without causing GI distress.",
                        "source_url": "https://www.trainingpeaks.com/blog/pre-workout-nutrition-what-to-eat-before-exercise/",
                    }
                ],
            }
        ],
        "personal_context_used": [
            "Endurance runner, ~60 miles/week training volume",
            "Tolerates higher sugar/sodium around training windows",
            "Avoids high-fat, high-fiber foods within 2 hours of a run",
        ],
        "history_note": "Similar to other quick-carb snacks you've logged as pre-run fuel without issue.",
        "swap": "If you want more protein for recovery instead of pre-run fuel, pair it with a scoop of whey in water.",
    },
    ("sports-drink", "diabetic"): {
        "verdict": "avoid",
        "headline": "21g of straight sugar in one bottle, Maria.",
        "reasoning": (
            "Gatorade is formulated to spike blood glucose fast — that's the "
            "point for athletes, but it's the opposite of what's recommended "
            "for Type 2 diabetes management outside of a hypoglycemic episode."
        ),
        "flagged": [
            {
                "item": "sugar, dextrose",
                "concern": "21g added sugar with zero fiber or protein to slow uptake.",
                "evidence": [
                    {
                        "claim": "Sugar-sweetened beverages are one of the most significant dietary contributors to blood glucose spikes in people with diabetes.",
                        "source_url": "https://www.diabetes.org/healthy-living/recipes-nutrition/eating-well/sugary-drinks",
                    }
                ],
            }
        ],
        "personal_context_used": [
            "Type 2 diabetes, doctor-recommended 25g/day added sugar cap",
            "Avoids high-glycemic-index foods",
        ],
        "history_note": "This alone would use over 80% of your daily added-sugar budget in one bottle.",
        "swap": "Try sparkling water with a splash of lime and a pinch of salt if you need electrolytes without the sugar.",
    },
    ("sports-drink", "athlete"): {
        "verdict": "eat",
        "headline": "Exactly what it's designed for, Jordan.",
        "reasoning": (
            "160mg sodium and 45mg potassium alongside 21g of fast carbs is "
            "textbook mid-run fueling for a 60-mile/week training load — "
            "this is a well-timed use case, not an everyday beverage."
        ),
        "flagged": [],
        "personal_context_used": [
            "Endurance runner, tolerates higher sugar/sodium around training windows",
            "Prioritizes electrolytes and fast carbs over fiber near workouts",
        ],
        "history_note": "Consistent with the electrolyte replacement strategy you've used on past long runs.",
        "swap": "No swap needed for training use — save the fancier electrolyte tabs for ultra-distance days.",
    },
    ("greek-yogurt", "diabetic"): {
        "verdict": "eat",
        "headline": "A genuinely good choice, Maria.",
        "reasoning": (
            "Plain whole-milk Greek yogurt has zero added sugar and 19g of "
            "protein per serving, which slows any natural-sugar absorption "
            "and helps blunt blood glucose response — this lines up well "
            "with your diet management goals."
        ),
        "flagged": [],
        "personal_context_used": [
            "Type 2 diabetes, prefers snacks with protein/fiber to slow glucose absorption",
        ],
        "history_note": "Similar high-protein, no-added-sugar snacks have worked well for you in the past.",
        "swap": "If you want more fiber, stir in a tablespoon of chia seeds or a handful of berries.",
    },
    ("greek-yogurt", "athlete"): {
        "verdict": "moderate",
        "headline": "Good, but not your best pre-run pick, Jordan.",
        "reasoning": (
            "19g of protein makes this excellent for recovery, but the fat "
            "content (9g) and lack of fast carbs mean it's not ideal within "
            "2 hours of a run given your history of GI distress with "
            "higher-fat foods close to training."
        ),
        "flagged": [
            {
                "item": "whole milk fat content",
                "concern": "9g of fat may slow digestion before a run.",
                "evidence": [
                    {
                        "claim": "High-fat, high-protein foods eaten close to endurance exercise can increase risk of GI distress due to slower gastric emptying.",
                        "source_url": "https://www.trainingpeaks.com/blog/pre-workout-nutrition-what-to-eat-before-exercise/",
                    }
                ],
            }
        ],
        "personal_context_used": [
            "Avoids high-fat foods within 2 hours of a run due to past GI distress",
            "Prioritizes recovery protein post-workout",
        ],
        "history_note": "Best used as a post-run recovery snack rather than pre-run fuel, based on your training patterns.",
        "swap": "Save this for post-run recovery; grab a banana or dates if you need something pre-run.",
    },
}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    if request.product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail=f"Unknown product_id: {request.product_id}")
    if request.persona_id not in PERSONAS:
        raise HTTPException(status_code=404, detail=f"Unknown persona_id: {request.persona_id}")

    # --- MOCK MODE (current) -------------------------------------------
    # TODO(real-integration): replace this lookup with the real pipeline:
    #   context = await memory.get_context(request.persona_id)
    #   product = PRODUCTS[request.product_id]
    #   evidence = await evidence.get_evidence(product["ingredients"])
    #   return await synthesis.synthesize(product, context, evidence)
    key = (request.product_id, request.persona_id)
    mock = MOCK_RESPONSES.get(key)
    if mock is None:
        raise HTTPException(status_code=404, detail=f"No mock response for {key}")
    return EvaluateResponse(**mock)
