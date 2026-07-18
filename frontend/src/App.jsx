import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import DemoApp from './demo/DemoApp'
import { supabase } from './lib/supabase'
import LoginPage from './pages/LoginPage'
import ProductSearchPage from './pages/ProductSearchPage'

function App() {
  const [session, setSession] = useState(undefined)

  useEffect(() => {
    if (!supabase) {
      setSession(null)
      return undefined
    }

    let active = true

    supabase.auth.getSession().then(({ data }) => {
      if (active) {
        setSession(data.session)
      }
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
    })

    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [])

  if (session === undefined) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 text-slate-500">
        Loading…
      </main>
    )
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/demo" element={<DemoApp />} />
        <Route
          path="/login"
          element={session ? <Navigate to="/app" replace /> : <LoginPage />}
        />
        <Route
          path="/app"
          element={
            session ? (
              <ProductSearchPage user={session.user} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route path="*" element={<Navigate to={session ? '/app' : '/login'} replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
