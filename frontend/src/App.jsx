import React, { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import Chrome from './components/Chrome.jsx'
import Landing from './components/Landing.jsx'
import Login from './components/Login.jsx'
import Dashboard from './components/Dashboard.jsx'
import Claims from './components/Claims.jsx'
import UploadFlow from './components/UploadFlow.jsx'
import ReviewScreen from './components/ReviewScreen.jsx'
import Reports from './components/Reports.jsx'

const SESSION_KEY = 'claimbridge.session'

export default function App() {
  const [view, setView] = useState('landing')   // landing | login | app
  const [tab, setTab] = useState('dashboard')    // dashboard | upload | claims | review | reports
  const [session, setSession] = useState(null)
  const [claims, setClaims] = useState([])
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)

  useEffect(() => {
    const saved = localStorage.getItem(SESSION_KEY)
    if (saved) { setSession(JSON.parse(saved)); setView('app') }
  }, [])

  const refresh = useCallback(() => {
    api.listClaims().then(setClaims).catch(() => {})
  }, [])

  useEffect(() => { if (view === 'app') refresh() }, [view, refresh])

  const say = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3600)
  }

  const handleLogin = (s) => {
    setSession(s)
    localStorage.setItem(SESSION_KEY, JSON.stringify(s))
    setTab('dashboard')
    setView('app')
    say(`Welcome, ${s.name}`)
  }

  const handleLogout = async () => {
    try {
      await fetch('/api/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: session?.token }),
      })
    } catch {}
    localStorage.removeItem(SESSION_KEY)
    setSession(null)
    setView('landing')
  }

  const go = (t) => { setTab(t); if (t !== 'review') refresh() }

  const openClaim = (id) => { setSelected(id); setTab('review') }

  if (view === 'landing') return <Landing onSignIn={() => setView('login')} />
  if (view === 'login') return <Login onLogin={handleLogin} onBack={() => setView('landing')} />

  return (
    <>
      <Chrome active={tab} go={go} session={session} onLogout={handleLogout} />

      {tab === 'dashboard' && (
        <Dashboard claims={claims} onOpen={openClaim} onViewAll={() => go('claims')} />
      )}
      {tab === 'claims' && <Claims claims={claims} onOpen={openClaim} />}
      {tab === 'upload' && (
        <UploadFlow say={say} onOpenReview={(id) => { refresh(); openClaim(id) }}
          onCancel={() => go('dashboard')} />
      )}
      {tab === 'review' && (
        <ReviewScreen claims={claims} selected={selected} setSelected={setSelected}
          onChanged={refresh} onBack={() => go('claims')} say={say} />
      )}
      {tab === 'reports' && <Reports />}

      {toast && <div className="toast">{toast}</div>}
    </>
  )
}
