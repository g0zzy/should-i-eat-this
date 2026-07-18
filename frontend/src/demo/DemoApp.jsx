import { useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const PERSONAS = [
  { id: 'diabetic', name: 'Maria Chen — Type 2 diabetic' },
  { id: 'athlete', name: 'Jordan Reyes — Endurance athlete' },
]

const PRODUCTS = [
  { id: 'granola-bar', name: 'Nature Valley Oats & Honey Granola Bar' },
  { id: 'sports-drink', name: 'Gatorade Thirst Quencher (Lemon-Lime)' },
  { id: 'greek-yogurt', name: 'Chobani Plain Greek Yogurt (Whole Milk)' },
]

const VERDICT_STYLES = {
  eat: {
    label: 'Eat',
    card: 'border-emerald-300 bg-emerald-50',
    badge: 'bg-emerald-600 text-white',
  },
  moderate: {
    label: 'Moderate',
    card: 'border-amber-300 bg-amber-50',
    badge: 'bg-amber-500 text-white',
  },
  avoid: {
    label: 'Avoid',
    card: 'border-rose-300 bg-rose-50',
    badge: 'bg-rose-600 text-white',
  },
}

function VerdictCard({ result }) {
  const style = VERDICT_STYLES[result.verdict] ?? VERDICT_STYLES.moderate

  return (
    <div className={`rounded-2xl border-2 p-6 shadow-sm ${style.card}`}>
      <div className="flex items-center gap-3">
        <span className={`rounded-full px-3 py-1 text-sm font-semibold uppercase tracking-wide ${style.badge}`}>
          {style.label}
        </span>
      </div>

      <h2 className="mt-4 text-2xl font-bold text-slate-900">{result.headline}</h2>
      <p className="mt-2 leading-relaxed text-slate-700">{result.reasoning}</p>

      {result.flagged.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Flagged</h3>
          <ul className="mt-2 space-y-3">
            {result.flagged.map((f, i) => (
              <li key={i} className="rounded-lg border border-slate-200 bg-white/70 p-3">
                <p className="font-medium text-slate-900">{f.item}</p>
                <p className="text-sm text-slate-600">{f.concern}</p>
                {f.evidence.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {f.evidence.map((e, j) => (
                      <li key={j} className="text-sm">
                        <a
                          href={e.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-indigo-600 underline decoration-indigo-300 underline-offset-2 hover:text-indigo-800"
                        >
                          {e.claim}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.personal_context_used.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Personal context used
          </h3>
          <ul className="mt-2 flex flex-wrap gap-2">
            {result.personal_context_used.map((c, i) => (
              <li
                key={i}
                className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs text-slate-600"
              >
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.history_note && (
        <p className="mt-4 rounded-lg bg-slate-100 p-3 text-sm italic text-slate-600">
          {result.history_note}
        </p>
      )}

      {result.swap && (
        <div className="mt-6 rounded-lg border border-indigo-200 bg-indigo-50 p-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-indigo-500">
            Suggested swap
          </h3>
          <p className="mt-1 text-slate-800">{result.swap}</p>
        </div>
      )}
    </div>
  )
}

function DemoApp() {
  const [personaId, setPersonaId] = useState(PERSONAS[0].id)
  const [productId, setProductId] = useState(PRODUCTS[0].id)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleEvaluate() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(`${API_URL}/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: productId, persona_id: personaId }),
      })
      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`)
      }
      const data = await res.json()
      setResult(data)
    } catch (err) {
      const message =
        err instanceof TypeError
          ? `Cannot reach the API at ${API_URL}. Start the FastAPI backend on port 8000 and try again.`
          : err.message || 'Something went wrong'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-2xl">
        <header className="text-center">
          <h1 className="text-4xl font-bold text-slate-900">Should I Eat This?</h1>
          <p className="mt-2 text-slate-500">
            A personalized verdict, grounded in live evidence and what we remember about you.
          </p>
        </header>

        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Who</span>
              <select
                value={personaId}
                onChange={(e) => setPersonaId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-200"
              >
                {PERSONAS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-sm font-medium text-slate-700">Product</span>
              <select
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-200"
              >
                {PRODUCTS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <button
            type="button"
            onClick={handleEvaluate}
            disabled={loading}
            className="mt-6 w-full rounded-lg bg-indigo-600 px-4 py-2.5 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? 'Evaluating…' : 'Evaluate'}
          </button>
        </div>

        <div className="mt-6">
          {error && (
            <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">
              {error}
            </div>
          )}
          {result && <VerdictCard result={result} />}
        </div>
      </div>
    </div>
  )
}

export default DemoApp
