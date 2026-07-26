import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { inr, statusMeta } from '../format.js'

/* Review — two-pane layout from Review.dc.html. Left: the scanned source
   document. Right: extracted fields grouped, with the signature amber-<85%
   confirm flow on coded fields (the only fields the engine assigns a
   confidence to). Footer approves -> builds the FHIR bundle.

   Everything is wired to the real API: GET claim, PUT (re-validate),
   POST approve, GET bundle, GET document preview. */

const CircleCheck = ({ stroke = 'var(--teal)' }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2">
    <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10Z" /><path d="m9 12 2 2 4-4" />
  </svg>
)
const Triangle = ({ stroke }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2">
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" /><path d="M12 9v4" /><path d="M12 17h.01" />
  </svg>
)

/* ---- scanned document viewer (image, with text-layer fallback) ---- */
function DocPane({ claimId, documents }) {
  const [doc, setDoc] = useState(documents[0])
  const [text, setText] = useState(null)
  const [imgOk, setImgOk] = useState(true)

  useEffect(() => { setDoc(documents[0]); setText(null); setImgOk(true) }, [documents, claimId])

  const fallbackToText = async () => {
    setImgOk(false)
    try {
      const res = await fetch(api.previewUrl(claimId, doc))
      const data = await res.json()
      setText(data.text || '(no text layer)')
    } catch { setText('(preview unavailable)') }
  }

  return (
    <div className="doc-pane">
      <div className="doc-pane-head">
        <div className="k">SCANNED DOCUMENT</div>
        <div className="doc-tools">
          {documents.length > 1 && (
            <select value={doc} onChange={(e) => { setDoc(e.target.value); setImgOk(true); setText(null) }}>
              {documents.map((d) => <option key={d}>{d}</option>)}
            </select>
          )}
        </div>
      </div>
      <div className="doc-view">
        {!documents.length ? (
          <div className="placeholder">No source documents stored for this claim.</div>
        ) : imgOk && !text ? (
          <img src={api.previewUrl(claimId, doc)} alt={`Preview of ${doc}`} onError={fallbackToText} />
        ) : (
          <pre>{text ?? 'Loading…'}</pre>
        )}
      </div>
      {documents.length > 0 && (
        <div className="doc-caption">{doc}</div>
      )}
    </div>
  )
}

export default function ReviewScreen({ claims, selected, setSelected, onChanged, onBack, say }) {
  const [detail, setDetail] = useState(null)
  const [ext, setExt] = useState(null)
  const [confirmed, setConfirmed] = useState({})
  const [busy, setBusy] = useState(false)

  const load = (id) => {
    api.getClaim(id)
      .then((d) => { setDetail(d); setExt(d.extraction); setConfirmed({}) })
      .catch(() => {})
  }
  useEffect(() => {
    if (selected) load(selected)
    else if (claims.length) setSelected(claims[0].id)
  }, [selected, claims]) // eslint-disable-line

  // --- nested setters --------------------------------------------------
  const setPath = (path, val) => setExt((prev) => {
    const next = structuredClone(prev)
    const keys = path.split('.')
    let node = next
    for (let i = 0; i < keys.length - 1; i++) node = node[keys[i]] ||= {}
    node[keys.at(-1)] = val || null
    return next
  })
  const setArr = (arr, i, key, val) => setExt((prev) => {
    const next = structuredClone(prev)
    next[arr][i][key] = val || null
    return next
  })

  // --- build the grouped field model from real extraction --------------
  const groups = useMemo(() => {
    if (!ext) return []
    const p = ext.patient || {}
    const e = ext.encounter || {}
    const cov = ext.coverage || {}
    const b = ext.billing || {}
    const nItems = (b.line_items || []).length

    const g = [
      {
        name: 'Patient & Identifiers',
        items: [
          { id: 'name', label: 'Patient name', value: p.name, onChange: (v) => setPath('patient.name', v) },
          { id: 'uhid', label: 'UHID', value: p.uhid, onChange: (v) => setPath('patient.uhid', v) },
          { id: 'insurer', label: 'Insurer', value: cov.insurer, onChange: (v) => setPath('coverage.insurer', v) },
          { id: 'policy', label: 'Policy number', value: cov.policy_number, onChange: (v) => setPath('coverage.policy_number', v) },
        ],
      },
      {
        name: 'Diagnosis & Procedure',
        items: [
          ...(ext.diagnoses || []).map((dx, i) => ({
            id: `dx-${i}`, label: `Diagnosis · ${dx.text}`, value: dx.icd10_code,
            onChange: (v) => setArr('diagnoses', i, 'icd10_code', v),
            confidence: dx.coding_confidence, confirmable: true,
          })),
          ...(ext.procedures || []).map((pr, i) => ({
            id: `pr-${i}`, label: `Procedure · ${pr.text}`, value: pr.snomed_code,
            onChange: (v) => setArr('procedures', i, 'snomed_code', v),
            confidence: pr.coding_confidence, confirmable: true,
          })),
        ],
      },
      {
        name: 'Admission',
        items: [
          { id: 'adm', label: 'Admission date', value: e.admission_datetime, onChange: (v) => setPath('encounter.admission_datetime', v) },
          { id: 'dis', label: 'Discharge date', value: e.discharge_datetime, onChange: (v) => setPath('encounter.discharge_datetime', v) },
          { id: 'ip', label: 'IP number', value: e.ip_number, onChange: (v) => setPath('encounter.ip_number', v) },
        ],
      },
      {
        name: 'Charges',
        items: [
          { id: 'sub', label: `Itemized charges (${nItems} item${nItems === 1 ? '' : 's'})`, value: b.sub_total, display: inr(b.sub_total), onChange: (v) => setPath('billing.sub_total', v) },
          { id: 'grand', label: 'Grand total', value: b.grand_total, display: inr(b.grand_total), onChange: (v) => setPath('billing.grand_total', v) },
        ],
      },
    ]
    return g.filter((grp) => grp.items.length)
  }, [ext])

  const flaggedRemaining = useMemo(() => {
    let n = 0
    groups.forEach((grp) => grp.items.forEach((f) => {
      if (f.confirmable && f.confidence != null && f.confidence < 0.85 && !confirmed[f.id]) n++
    }))
    return n
  }, [groups, confirmed])

  if (!claims.length) {
    return (
      <div className="page">
        <h1 className="page-title">Review</h1>
        <div className="empty" style={{ marginTop: 24 }}>
          <div className="big">Nothing to review yet</div>
          Process a claim from the Upload tab first.
        </div>
      </div>
    )
  }
  if (!detail || !ext) return <div className="page"><p className="page-sub">Loading…</p></div>

  const report = detail.validation
  const p = ext.patient || {}
  const cov = ext.coverage || {}
  const status = detail.approved ? 'APPROVED' : (report?.status || 'DRAFT')
  const meta = statusMeta(status)

  const save = async () => {
    setBusy(true)
    try {
      const res = await api.updateClaim(detail.id, ext)
      say(`Saved & re-validated: ${res.status}`)
      load(detail.id); onChanged()
    } catch (err) { say(String(err.message || err)) }
    finally { setBusy(false) }
  }

  const approve = async () => {
    setBusy(true)
    try {
      // Persist any edits first so the bundle reflects what the clerk sees.
      await api.updateClaim(detail.id, ext)
      await api.approve(detail.id)
      say('Approved — FHIR bundle built. Download it below or from Claims.')
      load(detail.id); onChanged()
    } catch (err) { say(String(err.message || err)) }
    finally { setBusy(false) }
  }

  const checks = report?.checks || []
  const canApprove = !detail.approved && report && report.status !== 'FAIL' && flaggedRemaining === 0

  const approveLabel = detail.approved ? 'Approved ✓'
    : flaggedRemaining > 0 ? `Confirm ${flaggedRemaining} field${flaggedRemaining > 1 ? 's' : ''} to continue`
    : report?.status === 'FAIL' ? 'Fix failing checks to approve'
    : 'Approve and build FHIR bundle'

  return (
    <div className="review">
      <div className="review-top">
        <button className="backlink" onClick={onBack}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6" /></svg>
          Claims
        </button>
        <div className="review-headrow">
          <h1>Review claim {detail.id}</h1>
          <div className="review-meta" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span>{p.name || '—'}{cov.insurer ? ` · ${cov.insurer}` : ''}</span>
            <span className={`pill ${meta.cls}`}>{meta.label}</span>
          </div>
        </div>
      </div>

      <div className="review-grid">
        <DocPane claimId={detail.id} documents={detail.documents} />

        <div className="fields-pane">
          {groups.map((grp) => (
            <div className="field-group" key={grp.name}>
              <div className="field-group-name">{grp.name}</div>
              <div className="field-list">
                {grp.items.map((f) => {
                  const pct = f.confidence != null ? Math.round(f.confidence * 100) : null
                  const needsConfirm = f.confirmable && f.confidence != null && f.confidence < 0.85 && !confirmed[f.id]
                  const isConfirmed = f.confirmable && f.confidence != null && f.confidence < 0.85 && confirmed[f.id]
                  return (
                    <div className={`frow ${needsConfirm ? 'warn' : ''}`} key={f.id}>
                      <div className="fmain">
                        <div className="flabel">{f.label}</div>
                        <input className="fvalue" value={f.value ?? ''}
                          onChange={(e) => f.onChange(e.target.value)}
                          placeholder="—" />
                      </div>
                      <div className="fside">
                        {needsConfirm && (
                          <>
                            <span className="conf-chip warn">{pct}%</span>
                            <button className="confirm-btn" onClick={() => setConfirmed((c) => ({ ...c, [f.id]: true }))}>Confirm</button>
                          </>
                        )}
                        {isConfirmed && (
                          <><span className="confirmed-txt">Confirmed</span><CircleCheck /></>
                        )}
                        {!needsConfirm && !isConfirmed && pct != null && (
                          <><span className="conf-chip good">{pct}%</span><CircleCheck /></>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}

          {report && (
            <div className="checklist">
              <div className="checklist-title">Validation checklist · {report.status}</div>
              {checks.map((c, i) => {
                const cls = c.result === 'PASS' ? 'pass' : c.result === 'FAIL' ? 'fail' : 'warn'
                return (
                  <div className={`check-item ${cls}`} key={i}>
                    {c.result === 'PASS'
                      ? <CircleCheck />
                      : <Triangle stroke={c.result === 'FAIL' ? 'var(--red)' : 'var(--amber)'} />}
                    <span>{c.check}{c.detail ? ` — ${c.detail}` : ''}</span>
                  </div>
                )
              })}
              {checks.length === 0 && <div className="check-item pass"><CircleCheck /><span>No checks recorded.</span></div>}
            </div>
          )}
        </div>
      </div>

      <div className="review-foot">
        {detail.approved && (
          <a className="btn ghost" href={api.bundleUrl(detail.id)}>Download FHIR bundle</a>
        )}
        <button className="btn ghost" disabled={busy} onClick={save}>Save draft</button>
        <button className="btn primary" disabled={busy || !canApprove} onClick={approve}>
          {approveLabel}
        </button>
      </div>
    </div>
  )
}
