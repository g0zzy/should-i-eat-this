You are building "should-i-eat-this" — a 4-hour, 2-person hackathon app. Treat this
document as the source of truth. If any request conflicts with it, flag the conflict
and default to what is written here. Do not add features not listed under IN SCOPE.

THE ONE-SENTENCE VISION
Yuka and Cal AI give a verdict about a PRODUCT. We give a verdict about a DECISION:
should THIS person eat THIS product, right now — reasoned against a persistent memory
of them (Cognee) and live, cited science (Tavily).

THE ONE DEMO MOMENT (everything serves this)
Same product, change the persona dropdown, hit Evaluate → the verdict card FLIPS
(e.g. red "AVOID for you" → green "EAT, you're fueling for training"), the "Why, for
you" chips name the personal constraint that drove it, and the flagged ingredients show
clickable Tavily source links. If a change does not make this moment work better, do not
make it.

IN SCOPE (build only this)
- One page. Persona <select>, Product <select>, Evaluate button, one verdict card.
- 2 personas, 3 hardcoded products (paste/seed data — NO OCR, NO barcode, NO camera).
- Backend: POST /evaluate {product_id, persona_id} -> the frozen JSON contract.
- memory.py (Cognee context), evidence.py (Tavily), synthesis.py (LLM fusion).
- Color-coded verdict, "Why for you" chips, clickable citations, suggested swap.

EXPLICITLY OUT OF SCOPE (refuse these)
- Auth, accounts, user signup, databases beyond Cognee's local store.
- OCR, barcode scanning, image upload, camera, mobile app.
- Multi-page UI, routing, settings screens, history screens.
- More than 2 personas or 3 products (until the demo works end to end).
- Real-time streaming, websockets, deployment/hosting config.

RULES
- schema.py is FROZEN. Never change field names.
- MOCK-FIRST: the app must run end to end on mock data before any real integration.
- The verdict MUST be driven by persona context. Same product + different persona
  must be able to produce a different verdict. This is non-negotiable.
- Never invent a citation source_url. Every claim traces to Tavily output.
- Each module is owned by one dev and testable in isolation (test_*.py).
- If Cognee blocks progress past a timebox, fall back to a structured context string
  with the SAME function signature — keep the "memory graph" framing intact.

WHEN UNSURE
Ask: "does this make the one demo moment work better, faster, or more reliably?"
If no, don't build it.
