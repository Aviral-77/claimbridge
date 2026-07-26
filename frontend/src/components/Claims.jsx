import React, { useMemo, useState } from 'react'
import { inr, statusMeta } from '../format.js'

/* Claims — full list from Claims.dc.html. Search + status-filter chips over
   the real /api/claims feed. Row click opens the Review screen. Columns are
   bound to fields the summary endpoint actually returns (id, patient, uhid,
   amount, status, flags) rather than inventing insurer/diagnosis columns. */

const FILTERS = [
  ['all', 'All'],
  ['REVIEW', 'Needs review'],
  ['PASS', 'Ready'],
  ['APPROVED', 'Approved'],
  ['FAIL', 'Failed'],
]

const GRID = { gridTemplateColumns: '1.2fr 2fr 1fr 1.2fr 40px' }

export default function Claims({ claims, onOpen }) {
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return claims.filter((c) => {
      if (filter !== 'all' && c.status !== filter) return false
      if (!q) return true
      return (c.id || '').toLowerCase().includes(q) ||
        (c.patient || '').toLowerCase().includes(q) ||
        (c.uhid || '').toLowerCase().includes(q)
    })
  }, [claims, filter, query])

  return (
    <div className="page">
      <h1 className="page-title" style={{ marginBottom: 32 }}>Claims</h1>

      <div className="searchbar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted-2)" strokeWidth="2">
          <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
        </svg>
        <input placeholder="Search patient, UHID or claim ID…"
          value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>

      <div className="chips">
        {FILTERS.map(([key, label]) => (
          <div key={key} className={`chip ${filter === key ? 'active' : ''}`}
            onClick={() => setFilter(key)}>{label}</div>
        ))}
      </div>

      <div className="dtable">
        <div className="dtable-head" style={GRID}>
          <div className="col-h">CLAIM ID</div>
          <div className="col-h">PATIENT</div>
          <div className="col-h t-right">AMOUNT</div>
          <div className="col-h">STATUS</div>
          <div />
        </div>

        {claims.length === 0 ? (
          <div className="empty">
            <div className="big">No claims yet</div>
            Process a patient's documents from the Upload tab.
          </div>
        ) : rows.length === 0 ? (
          <div className="empty">
            <div className="big">No claims match</div>
            Try a different filter or search term.
          </div>
        ) : rows.map((c) => {
          const s = statusMeta(c.status)
          return (
            <div key={c.id} className="dtable-row" style={GRID} onClick={() => onOpen(c.id)}>
              <div className="cell-id">{c.id}</div>
              <div>
                <div className="cell-name">{c.patient || '—'}</div>
                {c.uhid && <div className="cell-sub">{c.uhid}</div>}
              </div>
              <div className="cell-amt">{inr(c.amount)}</div>
              <div>
                <span className={`pill ${s.cls}`}>{s.label}</span>
                {c.status === 'REVIEW' && c.flags > 0 && (
                  <div className="cell-sub" style={{ marginTop: 5 }}>
                    {c.flags} field{c.flags > 1 ? 's' : ''} below 85%
                  </div>
                )}
              </div>
              <div className="chev">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="m9 18 6-6-6-6" />
                </svg>
              </div>
            </div>
          )
        })}
      </div>

      {claims.length > 0 && (
        <div className="pager">
          <div className="page-sub">
            Showing {rows.length} of {claims.length} claim{claims.length > 1 ? 's' : ''}
          </div>
        </div>
      )}
    </div>
  )
}
