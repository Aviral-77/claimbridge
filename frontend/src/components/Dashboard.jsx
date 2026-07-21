import React from 'react'
import { api } from '../api.js'

const inr = (n) => (n == null ? '—' : `₹${Number(n).toLocaleString('en-IN')}`)

export default function Dashboard({ claims, onOpen }) {
  const passing = claims.filter((c) => c.status === 'PASS' || c.status === 'APPROVED')
  const review = claims.filter((c) => c.status === 'REVIEW')
  const approved = claims.filter((c) => c.status === 'APPROVED')
  const total = claims.reduce((s, c) => s + (c.amount || 0), 0)

  return (
    <>
      <h1>Claims</h1>
      <p className="sub">Every cashless claim, from upload to settlement</p>

      <div className="stats">
        <div className="card stat"><div className="k">Claims</div>
          <div className="v">{claims.length}</div></div>
        <div className="card stat"><div className="k">Need your review</div>
          <div className={`v ${review.length ? 'amber' : ''}`}>{review.length}</div></div>
        <div className="card stat"><div className="k">Approved (FHIR built)</div>
          <div className="v">{approved.length}</div></div>
        <div className="card stat"><div className="k">Total claim value</div>
          <div className="v mono" style={{ fontSize: 21 }}>{inr(total)}</div></div>
      </div>

      <div className="card">
        {claims.length === 0 ? (
          <div className="empty">
            <div className="big">No claims yet</div>
            Upload a patient's documents to process your first claim.
          </div>
        ) : (
          <table className="claims-table">
            <thead>
              <tr><th>Claim</th><th>Patient</th><th className="amt">Amount</th>
                <th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {claims.map((c) => (
                <tr key={c.id} onClick={() => onOpen(c.id)}>
                  <td className="mono" style={{ fontSize: 12.5 }}>{c.id}</td>
                  <td>
                    <b>{c.patient || '—'}</b>
                    <div className="muted mono">{c.uhid || ''}</div>
                  </td>
                  <td className="amt mono">{inr(c.amount)}</td>
                  <td>
                    <span className={`pill ${c.status}`}>{c.status}</span>
                    {c.status === 'REVIEW' && c.flags > 0 && (
                      <span className="muted"> · {c.flags} flag{c.flags > 1 ? 's' : ''}</span>
                    )}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    {c.status === 'APPROVED' && (
                      <a className="btn ghost" style={{ padding: '6px 12px' }}
                        href={api.bundleUrl(c.id)}>FHIR bundle</a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
