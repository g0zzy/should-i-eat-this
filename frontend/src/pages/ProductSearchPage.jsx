import { useState } from 'react'

import { supabase } from '../lib/supabase'

function ProductSearchPage({ user }) {
  const [productName, setProductName] = useState('')
  const [submittedProduct, setSubmittedProduct] = useState('')
  const [signOutError, setSignOutError] = useState('')

  function handleSubmit(event) {
    event.preventDefault()
    setSubmittedProduct(productName.trim())
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
              className="rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white transition hover:bg-indigo-700"
            >
              Check
            </button>
          </form>

          {submittedProduct && (
            <div className="mt-6 rounded-lg border border-indigo-200 bg-indigo-50 p-4 text-slate-700">
              Ready to evaluate <strong>{submittedProduct}</strong>. Product lookup and
              recommendation will be connected next.
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

export default ProductSearchPage
