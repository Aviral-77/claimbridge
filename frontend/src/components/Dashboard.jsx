import React from 'react'
import { inr, statusMeta } from '../format.js'

/* Dashboard — overview from Dashboard.dc.html. Metric tiles and a
   "needs your attention" table, both computed from the REAL /api/claims
   feed (no fabricated business KPIs — operational counts only). */

const Chevron = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="m9 18 6-6-6-6" />
  </svg>
)

const GRID = { gridTemplateColumns: '1.1fr 1.6fr 1fr 1fr 1.2fr 40px' }

export default function Dashboard({ claims, onOpen, onViewAll }) {
  const review = claims.filter((c) => c.status === 'REVIEW')
  const approved = claims.filter((c) => c.status === 'APPROVED')
  const failed = claims.filter((c) => c.status === 'FAIL')
  const total = claims.reduce((s, c) => s + (c.amount || 0), 0)

  // Rows that need a human: flagged for review or failing validation.
  const attention = [...review, ...failed]

  return (
    <div className="page">
      <div style={{ marginBottom: 40 }}>
        <h1 className="page-title">Dashboard</h1>
        <div className="page-sub">Every cashless claim, from upload to settlement</div>
      </div>

      <div className="metrics">
        <div className="metric">
          <div className="label">Claims in console</div>
          <div className="value">{claims.length}</div>
        </div>
        <div className="metric">
          <div className="label">Awaiting review</div>
          <div className={`value ${review.length ? 'amber' : ''}`}>{review.length}</div>
        </div>
        <div className="metric">
          <div className="label">Approved · FHIR built</div>
          <div className="value teal">{approved.length}</div>
        </div>
        <div className="metric">
          <div className="label">Total claim value</div>
          <div className="value" style={{ fontSize: 26 }}>{inr(total)}</div>
        </div>
      </div>

      <div className="attention-head">
        <h2 className="section-title">Needs your attention</h2>
        <button className="linkish" onClick={onViewAll}>View all claims →</button>
      </div>

      <div className="dtable">
        <div className="dtable-head" style={GRID}>
          <div className="col-h">CLAIM ID</div>
          <div className="col-h">PATIENT</div>
          <div className="col-h">FLAGS</div>
          <div className="col-h t-right">AMOUNT</div>
          <div className="col-h">STATUS</div>
          <div />
        </div>

        {claims.length === 0 ? (
          <div className="empty">
            <div className="big">No claims yet</div>
            Upload a patient's documents to process your first claim.
          </div>
        ) : attention.length === 0 ? (
          <div className="empty">
            <div className="big">All clear</div>
            No claims are waiting on you right now.
          </div>
        ) : attention.map((c) => {
          const s = statusMeta(c.status)
          return (
            <div key={c.id} className="dtable-row" style={GRID} onClick={() => onOpen(c.id)}>
              <div className="cell-id">{c.id}</div>
              <div>
                <div className="cell-name">{c.patient || '—'}</div>
                {c.uhid && <div className="cell-sub">{c.uhid}</div>}
              </div>
              <div className="cell-muted">
                {c.flags > 0 ? `${c.flags} field${c.flags > 1 ? 's' : ''}` : '—'}
              </div>
              <div className="cell-amt">{inr(c.amount)}</div>
              <div><span className={`pill ${s.cls}`}>{s.label}</span></div>
              <div className="chev"><Chevron /></div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
