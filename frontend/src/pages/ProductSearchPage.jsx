import { useState } from 'react'

import { supabase } from '../lib/supabase'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function ProductSearchPage({ user }) {
  const [productName, setProductName] = useState('')
  const [resolution, setResolution] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [signOutError, setSignOutError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    const query = productName.trim()
    if (!query) return

    setLoading(true)
    setError('')
    setResolution(null)

    try {
      const response = await fetch(`${API_URL}/resolve-ingredients`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_name: query }),
      })
      const body = await response.json()

      if (!response.ok) {
        throw new Error(body.detail || `Request failed (${response.status})`)
      }

      setResolution(body)
    } catch (requestError) {
      const message =
        requestError instanceof TypeError
          ? `Cannot reach the API at ${API_URL}. Start the FastAPI backend and try again.`
          : requestError.message || 'Ingredient resolution failed.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSignOut() {
    setSignOutError('')
    const { error } = await supabase.auth.signOut()

    if (error) {
      setSignOutError(error.message)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12">
      <div className="mx-auto max-w-2xl">
        <header className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">
              Should I Eat This?
            </p>
            <p className="mt-1 text-sm text-slate-500">Signed in as {user.email}</p>
          </div>
          <button
            type="button"
            onClick={handleSignOut}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Sign out
          </button>
        </header>

        {signOutError && (
          <p className="mt-4 rounded-lg border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700">
            {signOutError}
          </p>
        )}

        <section className="mt-12 rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="text-3xl font-bold text-slate-900">What are you thinking of eating?</h1>
          <p className="mt-2 text-slate-500">
            Enter a product such as Snickers or REWE Bio Hummus.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-3 sm:flex-row">
            <label className="min-w-0 flex-1">
              <span className="sr-only">Product name</span>
              <input
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
                placeholder="Product name"
                required
                autoFocus
                className="w-full rounded-lg border border-slate-300 px-4 py-3 text-slate-900 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-200"
              />
            </label>

            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? 'Resolving…' : 'Check'}
            </button>
          </form>

          {error && (
            <div className="mt-6 rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">
              {error}
            </div>
          )}

          {resolution && resolution.source_type === 'none' && (
            <div className="mt-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-800">
              No trustworthy ingredient list was found for <strong>{resolution.product_name}</strong>.
              Try including the brand, flavor, or package variant.
            </div>
          )}

          {resolution && resolution.source_type === 'web' && (
            <div className="mt-8 space-y-6 border-t border-slate-200 pt-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-slate-500">Resolved product</p>
                  <h2 className="text-2xl font-bold text-slate-900">{resolution.product_name}</h2>
                </div>
                <div className="flex gap-2">
                  <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700">
                    {resolution.source_type}
                  </span>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
                      resolution.confidence === 'high'
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-amber-100 text-amber-700'
                    }`}
                  >
                    {resolution.confidence} confidence
                  </span>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Raw ingredients
                </h3>
                <ul className="mt-3 flex flex-wrap gap-2">
                  {resolution.ingredients.map((ingredient, index) => (
                    <li
                      key={`${ingredient}-${index}`}
                      className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-sm text-slate-700"
                    >
                      {ingredient}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-indigo-600">
                  Notable ingredients for the evidence step
                </h3>
                {resolution.notable_ingredients.length > 0 ? (
                  <ul className="mt-3 flex flex-wrap gap-2">
                    {resolution.notable_ingredients.map((ingredient, index) => (
                      <li
                        key={`${ingredient}-${index}`}
                        className="rounded-full bg-indigo-600 px-3 py-1 text-sm text-white"
                      >
                        {ingredient}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-indigo-800">
                    No ingredients need a separate evidence check.
                  </p>
                )}
              </div>

              <a
                href={resolution.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-block text-sm font-medium text-indigo-600 underline underline-offset-2 hover:text-indigo-800"
              >
                View ingredient source
              </a>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

export default ProductSearchPage
