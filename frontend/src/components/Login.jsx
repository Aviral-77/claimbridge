import React, { useState } from 'react'

export default function Login({ onLogin, onBack }) {
  const [email, setEmail] = useState('desk@skn.hospital')
  const [password, setPassword] = useState('claims123')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || 'Sign-in failed')
      onLogin(await res.json())
    } catch (err) {
      setError(String(err.message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="logo dark" style={{ marginBottom: 18 }}>
          <span className="logo-dot" />ClaimBridge
        </div>
        <h1 style={{ fontSize: 18, marginBottom: 4 }}>Sign in</h1>
        <p className="sub" style={{ marginBottom: 18 }}>
          Your hospital's claims console
        </p>

        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username"
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="pw">Password</label>
          <input id="pw" type="password" autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>

        {error && <p className="login-error">{error}</p>}

        <button className="btn primary" style={{ width: '100%', marginTop: 6 }}
          disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="muted" style={{ marginTop: 14, fontSize: 12 }}>
          Demo accounts: <span className="mono">desk@skn.hospital</span> or{' '}
          <span className="mono">admin@lifecare.in</span> — password{' '}
          <span className="mono">claims123</span>
        </p>
        <button type="button" className="linkish" onClick={onBack}>
          ← Back to site
        </button>
      </form>
    </div>
  )
}
