# should-i-eat-this

A personalized verdict on whether a specific food product is right for a specific
person — grounded in live web evidence and a persistent memory of that person.

**Current state: mock mode.** `/evaluate` returns hardcoded responses so the full
stack runs end to end. The real Cognee (memory) / Tavily (evidence) / LLM
(synthesis) integrations are stubbed out in `backend/memory.py`,
`backend/evidence.py`, and `backend/synthesis.py` with the correct function
signatures — see the `TODO(real-integration)` comments in each file.

## Backend

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in LLM_API_KEY / TAVILY_API_KEY when wiring up real integrations
uvicorn main:app --reload --port 8000
```

> **Note:** `cognee` transitively depends on `cbor2`, which needs a Rust
> toolchain to build from source if no prebuilt wheel matches your platform.
> Mock mode does not import `cognee` at runtime, so if `pip install` fails on
> `cbor2`, you can install everything else first and add `cognee` back once
> you have Rust (`rustup.rs`) or a matching wheel available:
> `pip install fastapi "uvicorn[standard]" pydantic python-dotenv tavily-python anthropic openai`

Backend runs at http://localhost:8000. Check http://localhost:8000/health.

## Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_URL defaults to http://localhost:8000
npm run dev
```

Frontend runs at http://localhost:5173 (Vite's default).

## Demo flow

1. Start both servers as above.
2. Open the frontend, pick a persona ("Maria Chen — Type 2 diabetic" or
   "Jordan Reyes — Endurance athlete"), pick a product, click **Evaluate**.
3. Try the **granola bar** with both personas — same product, opposite verdict
   (`avoid` for the diabetic, `eat` for the athlete). This is the core demo.

## Wiring up the real integrations

Once mock mode is confirmed working end to end:

1. `backend/memory.py` — implement `seed_personas()` and `get_context(persona_id)`
   using Cognee to persist and recall persona profiles from `backend/seed/personas.json`.
2. `backend/evidence.py` — implement `get_evidence(ingredients)` using Tavily to
   pull live citations for each ingredient.
3. `backend/synthesis.py` — implement `synthesize(product, context, evidence)`
   using the Anthropic or OpenAI SDK (toggle via `LLM_PROVIDER` in `.env`) to
   produce a real `EvaluateResponse`.
4. In `backend/main.py`, swap the `MOCK_RESPONSES` lookup in `evaluate()` for
   the real pipeline: `memory.get_context` → `evidence.get_evidence` →
   `synthesis.synthesize`.
