# should-i-eat-this

A personalized verdict on whether a specific food product is right for a specific
person — grounded in live web evidence and a persistent memory of that person.

**Current state: mock mode.** `/evaluate` returns hardcoded responses so the full
stack runs end to end. The real Tavily (evidence) / LLM (synthesis) integrations
are stubbed out in `backend/evidence.py` and `backend/synthesis.py` with the
correct function signatures — see the `TODO(real-integration)` comments in
each file. `backend/memory.py` is a **real, working integration** against
Cognee Cloud (see below) — it just isn't wired into `/evaluate` yet.

## Backend

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API keys — see "Memory (Cognee Cloud)" below
uvicorn main:app --reload --port 8000
```

Backend runs at http://localhost:8000. Check http://localhost:8000/health.

<<<<<<< Updated upstream
### Memory (Cognee Cloud)

Memory uses **Cognee Cloud** (https://platform.cognee.ai) via the lightweight
`cognee-sdk` client, not the full self-hosted `cognee` package — this avoids
a local vector/graph DB setup and a Rust toolchain requirement (the full
package's `cbor2` dependency needs Rust to build from source; the SDK is a
~5-10MB httpx-based REST client and needs neither).

1. Sign in at https://platform.cognee.ai (Google/GitHub OAuth) — a free
   workspace is created automatically.
2. Create an API key on the API Keys page and copy your tenant URL.
3. Fill in `COGNEE_API_URL` and `COGNEE_API_KEY` in `backend/.env`.
4. Seed the two personas once: `python -c "import asyncio, memory; asyncio.run(memory.seed_personas())"`

Memory is isolated per persona in an opaque Cognee dataset. Profiles are
structured and updated in place; food decisions are dated, append-only records.
The retrieval API accepts a product and returns only product-relevant profile
facts and prior reported outcomes. Seed the fictional POC history once with:

```bash
python -c "import asyncio, memory; asyncio.run(memory.seed_demo_memory())"
```

Do not run that command repeatedly against the same tenant: demo food events
are append-only. The primary API is
`memory.get_evaluation_context(persona_id, product, now)`. The older
`get_context(persona_id)` accessor remains for compatibility while mock mode is
active. Cognee is retrieval memory; a production application should also keep
the original structured profile and event records in its own database.
=======
### Tavily product and evidence endpoint

The product-name-first Tavily flow is exposed separately from the mocked
`/evaluate` route:

```bash
curl -X POST http://localhost:8000/resolve-and-evidence \
  -H "Content-Type: application/json" \
  -d '{"product_name":"Snickers","persona_id":"diabetic","include_debug":true}'
```

`backend/services/product_resolver.py` resolves the product label from Tavily;
`backend/services/evidence_service.py` then searches profile-relevant
clinical/public-health evidence. `TAVILY_API_KEY` is read from `backend/.env`.
>>>>>>> Stashed changes

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

1. `backend/memory.py` — **done.** Real Cognee Cloud integration for a
   structured profile and product-specific historical memory; run the seeding
   step above once you have API keys set.
2. `backend/evidence.py` — implement `get_evidence(ingredients)` using Tavily to
   pull live citations for each ingredient.
3. `backend/synthesis.py` — implement `synthesize(product, context, evidence)`
   using the Anthropic or OpenAI SDK (toggle via `LLM_PROVIDER` in `.env`) to
   produce a real `EvaluateResponse`.
4. In `backend/main.py`, swap the `MOCK_RESPONSES` lookup in `evaluate()` for
   the real pipeline: `memory.get_context` → `evidence.get_evidence` →
   `synthesis.synthesize`.
