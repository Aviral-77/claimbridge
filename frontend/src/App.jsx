import React, { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import Landing from './components/Landing.jsx'
import Login from './components/Login.jsx'
import Dashboard from './components/Dashboard.jsx'
import UploadFlow from './components/UploadFlow.jsx'
import ReviewScreen from './components/ReviewScreen.jsx'

const SESSION_KEY = 'claimbridge.session'

export default function App() {
  const [view, setView] = useState('landing')          // landing | login | app
  const [session, setSession] = useState(null)
  const [tab, setTab] = useState('claims')
  const [claims, setClaims] = useState([])
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)
  const [drawer, setDrawer] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem(SESSION_KEY)
    if (saved) {
      setSession(JSON.parse(saved))
      setView('app')
    }
  }, [])

  const refresh = useCallback(() => {
    api.listClaims().then(setClaims).catch(() => {})
  }, [])

  useEffect(() => { if (view === 'app') refresh() }, [view, refresh])

  const say = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3200)
  }

  const handleLogin = (s) => {
    setSession(s)
    localStorage.setItem(SESSION_KEY, JSON.stringify(s))
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
    setDrawer(false)
    setView('landing')
  }

  const openClaim = (id) => {
    setSelected(id)
    setTab('review')
  }

  if (view === 'landing') return <Landing onSignIn={() => setView('login')} />
  if (view === 'login') return (
    <Login onLogin={handleLogin} onBack={() => setView('landing')} />
  )

  return (
    <>
      <header className="topbar">
        <button className="burger" aria-label="Menu" aria-expanded={drawer}
          onClick={() => setDrawer(true)}>
          <span /><span /><span />
        </button>
        <div className="logo"><span className="logo-dot" />ClaimBridge</div>
        <nav className="nav">
          <button className={tab === 'claims' ? 'active' : ''}
            onClick={() => { setTab('claims'); refresh() }}>Claims</button>
          <button className={tab === 'upload' ? 'active' : ''}
            onClick={() => setTab('upload')}>Upload</button>
          <button className={tab === 'review' ? 'active' : ''}
            onClick={() => setTab('review')}>Review</button>
        </nav>
        <div className="who"><span>{session?.org} · </span><b>{session?.name}</b></div>
      </header>

      {drawer && (
        <div className="drawer-scrim" onClick={() => setDrawer(false)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}
            role="dialog" aria-label="Menu">
            <div className="drawer-head">
              <div className="logo dark"><span className="logo-dot" />ClaimBridge</div>
              <button className="drawer-x" aria-label="Close menu"
                onClick={() => setDrawer(false)}>×</button>
            </div>
            <div className="drawer-user">
              <b>{session?.name}</b>
              <div className="muted">{session?.email}</div>
              <div className="muted">{session?.org}</div>
            </div>
            <nav className="drawer-nav">
              {[['claims', 'Claims dashboard'], ['upload', 'Upload documents'],
                ['review', 'Review claims']].map(([k, label]) => (
                <button key={k} className={tab === k ? 'active' : ''}
                  onClick={() => { setTab(k); setDrawer(false) }}>
                  {label}
                </button>
              ))}
              <button disabled title="Coming with NHCX sandbox access">
                Submissions · NHCX <span className="soon">soon</span>
              </button>
              <button disabled title="Coming soon">
                Settings <span className="soon">soon</span>
              </button>
            </nav>
            <div className="drawer-foot">
              <button className="btn ghost" style={{ width: '100%' }}
                onClick={handleLogout}>Sign out</button>
            </div>
          </aside>
        </div>
      )}

      <main className="page">
        {tab === 'claims' && <Dashboard claims={claims} onOpen={openClaim} />}
        {tab === 'upload' && (
          <UploadFlow onDone={(id) => { refresh(); openClaim(id) }} say={say} />
        )}
        {tab === 'review' && (
          <ReviewScreen claims={claims} selected={selected}
            setSelected={setSelected} onChanged={refresh} say={say} />
        )}
      </main>

      {toast && <div className="toast">{toast}</div>}
    </>
  )
}
