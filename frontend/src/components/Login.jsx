import React, { useState } from 'react'

/* Login — split panel from Login.dc.html. Wired to POST /api/login (demo auth
   in api.py). Prefilled with a demo account so the console is one click away. */

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
    <div className="login">
      <div className="login-side">
        <div className="brand">
          <span className="brand-mark invert">CB</span>
          <span className="brand-word">ClaimBridge</span>
        </div>

        <div>
          <h1>The claims console for your hospital's billing desk.</h1>
          <div className="login-feats">
            <div className="login-feat">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1Z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
              <span>Bank-grade encryption for every scanned document and claim record</span>
            </div>
            <div className="login-feat">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                <path d="M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4" /><path d="M14 2v4a2 2 0 0 0 2 2h4" /><path d="m3.5 17.5 2 2 4-4.5" />
              </svg>
              <span>NHCX-compliant claim format, built in and kept current</span>
            </div>
            <div className="login-feat">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
              </svg>
              <span>Most billing desks are fully onboarded within a day</span>
            </div>
          </div>
        </div>

        <div className="login-side-foot">© 2026 ClaimBridge</div>
      </div>

      <div className="login-main">
        <form className="login-card" onSubmit={submit}>
          <div className="login-kicker">CLAIMS CONSOLE</div>
          <h2>Sign in</h2>
          <div className="sub">For authorized hospital billing staff only.</div>

          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" className="input" type="email" autoComplete="username"
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="pw">Password</label>
            <input id="pw" className="input" type="password" autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="forgot"><a href="#" onClick={(e) => e.preventDefault()}>Forgot password?</a></div>

          {error && <p className="login-error">{error}</p>}

          <button className="btn primary" style={{ width: '100%' }} disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>

          <div className="login-note">
            Demo accounts: <span className="mono">desk@skn.hospital</span> or{' '}
            <span className="mono">admin@lifecare.in</span> — password{' '}
            <span className="mono">claims123</span>. Do not share your password
            over phone or email.
          </div>
          <button type="button" className="linkish" style={{ marginTop: 16 }} onClick={onBack}>
            ← Back to site
          </button>
        </form>
      </div>
    </div>
  )
}
