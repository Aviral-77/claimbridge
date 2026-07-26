import React, { useRef } from 'react'

/* Shared top-nav app shell from the mockups: brand, primary tabs, user menu.
   `active` is the current tab key; `go` navigates; `session` drives the
   right-hand identity block. Review is reached from a claim row, so it is
   not a top-level tab — it lights up "Claims" while open. */

const TABS = [
  ['dashboard', 'Dashboard'],
  ['upload', 'Upload'],
  ['claims', 'Claims'],
  ['reports', 'Reports'],
]

const initials = (name = '') =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || 'CB'

export default function Chrome({ active, go, session, onLogout }) {
  const menuRef = useRef(null)
  const navActive = active === 'review' ? 'claims' : active

  return (
    <header className="chrome">
      <div className="chrome-left">
        <button className="brand" onClick={() => go('dashboard')} aria-label="ClaimBridge home">
          <span className="brand-mark">CB</span>
          <span className="brand-word">ClaimBridge</span>
        </button>
        <nav className="chrome-tabs">
          {TABS.map(([key, label]) => (
            <button key={key} className={navActive === key ? 'active' : ''}
              onClick={() => go(key)}>
              {label}
            </button>
          ))}
        </nav>
      </div>

      <details className="usermenu" ref={menuRef}>
        <summary>
          <div className="usermenu-who">
            <b>{session?.org || 'Hospital'}</b>
            <span>{session?.name || 'Claims Desk'}</span>
          </div>
          <div className="avatar">{initials(session?.org || session?.name)}</div>
        </summary>
        <div className="usermenu-pop">
          <div className="soonrow">
            <span>Settings</span><span className="tag-soon">SOON</span>
          </div>
          <div className="sep" />
          <button onClick={() => { menuRef.current?.removeAttribute('open'); onLogout() }}>
            Sign out
          </button>
        </div>
      </details>
    </header>
  )
}
