import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const inr = (n) => (n == null ? '—' : `₹${Number(n).toLocaleString('en-IN')}`)

function XField({ label, value, onChange, confidence, mono }) {
  const warn = confidence != null && confidence < 0.85
  return (
    <div className={`xfield ${warn ? 'warn' : ''}`}>
      <label>{label}</label>
      <div className="box">
        <input className={mono ? 'mono' : ''} value={value || ''}
          onChange={(e) => onChange(e.target.value)} />
        {confidence != null && (
          <span className="conf">
            {Math.round(confidence * 100)}%{warn ? ' — confirm' : ''}
          </span>
        )}
      </div>
    </div>
  )
}

function DocPane({ claimId, documents }) {
  const [doc, setDoc] = useState(documents[0])
  const [text, setText] = useState(null)
  const [imgOk, setImgOk] = useState(true)

  useEffect(() => { setDoc(documents[0]); setText(null); setImgOk(true) }, [documents])

  useEffect(() => {
    if (!doc || !imgOk) return
    setText(null)
  }, [doc, imgOk])

  const fallbackToText = async () => {
    setImgOk(false)
    try {
      const res = await fetch(api.previewUrl(claimId, doc))
      const data = await res.json()
      setText(data.text || '(no text layer)')
    } catch { setText('(preview unavailable)') }
  }

  if (!documents.length) {
    return <div className="empty">No source documents stored for this claim.</div>
  }
  return (
    <div className="card doc-pane">
      <div className="doc-bar">
        <b>Source document</b>
        <select value={doc} onChange={(e) => { setDoc(e.target.value); setImgOk(true); setText(null) }}>
          {documents.map((d) => <option key={d}>{d}</option>)}
        </select>
      </div>
      <div className="doc-view">
        {imgOk && !text ? (
          <img src={api.previewUrl(claimId, doc)} alt={`Preview of ${doc}`}
            onError={fallbackToText} />
        ) : (
          <pre>{text ?? 'Loading…'}</pre>
        )}
      </div>
    </div>
  )
}

export default function ReviewScreen({ claims, selected, setSelected, onChanged, say }) {
  const [detail, setDetail] = useState(null)
  const [ext, setExt] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = (id) => {
    api.getClaim(id).then((d) => { setDetail(d); setExt(d.extraction) }).catch(() => {})
  }
  useEffect(() => {
    if (selected) load(selected)
    else if (claims.length) { setSelected(claims[0].id) }
  }, [selected, claims])

  if (!claims.length) {
    return (
      <>
        <h1>Review</h1>
        <div className="card empty">
          <div className="big">Nothing to review yet</div>
          Process a claim from the Upload tab first.
        </div>
      </>
    )
  }
  if (!detail || !ext) return <p className="sub">Loading…</p>

  const p = ext.patient || {}
  const e = ext.encounter || {}
  const cov = ext.coverage || {}
  const b = ext.billing || {}
  const report = detail.validation
  const set = (path, val) => {
    setExt((prev) => {
      const next = structuredClone(prev)
      const keys = path.split('.')
      let node = next
      for (let i = 0; i < keys.length - 1; i++) node = node[keys[i]] ||= {}
      node[keys.at(-1)] = val || null
      return next
    })
  }

  const save = async () => {
    setBusy(true)
    try {
      const res = await api.updateClaim(detail.id, ext)
      say(`Re-validated: ${res.status}`)
      load(detail.id); onChanged()
    } catch (err) { say(String(err.message || err)) }
    finally { setBusy(false) }
  }

  const approve = async () => {
    setBusy(true)
    try {
      await api.approve(detail.id)
      say('Approved — FHIR bundle built. Download it from the Claims tab.')
      load(detail.id); onChanged()
    } catch (err) { say(String(err.message || err)) }
    finally { setBusy(false) }
  }

  const flagged = (report?.checks || []).filter((c) => c.result !== 'PASS')

  return (
    <>
      <div className="review-head">
        <select value={detail.id} className="mono"
          style={{ border: '1px solid var(--line)', borderRadius: 7, padding: '7px 10px' }}
          onChange={(e) => setSelected(e.target.value)}>
          {claims.map((c) => <option key={c.id} value={c.id}>{c.id}</option>)}
        </select>
        <span className="who-name">{p.name || '—'}</span>
        <span className="muted mono">{p.uhid || ''} {e.ip_number ? `· ${e.ip_number}` : ''}</span>
        {report && <span className={`pill ${detail.approved ? 'APPROVED' : report.status}`}>
          {detail.approved ? 'APPROVED' : report.status}</span>}
      </div>

      <div className="review-grid">
        <DocPane claimId={detail.id} documents={detail.documents} />

        <div className="card form-pane">
          <h2>Extracted claim</h2>
          <div className="grid2">
            <XField label="Patient name" value={p.name} onChange={(v) => set('patient.name', v)} />
            <XField label="UHID" mono value={p.uhid} onChange={(v) => set('patient.uhid', v)} />
          </div>
          <div className="grid2">
            <XField label="Admission" mono value={e.admission_datetime}
              onChange={(v) => set('encounter.admission_datetime', v)} />
            <XField label="Discharge" mono value={e.discharge_datetime}
              onChange={(v) => set('encounter.discharge_datetime', v)} />
          </div>
          <div className="grid2">
            <XField label="Insurer" value={cov.insurer} onChange={(v) => set('coverage.insurer', v)} />
            <XField label="Policy no." mono value={cov.policy_number}
              onChange={(v) => set('coverage.policy_number', v)} />
          </div>

          <h2>Diagnoses</h2>
          {(ext.diagnoses || []).map((dx, i) => (
            <div className="grid2" key={i} style={{ alignItems: 'center' }}>
              <div style={{ fontSize: 13.5 }}>{dx.text}</div>
              <XField label="ICD-10" mono value={dx.icd10_code}
                confidence={dx.coding_confidence}
                onChange={(v) => setExt((prev) => {
                  const next = structuredClone(prev)
                  next.diagnoses[i].icd10_code = v || null
                  return next
                })} />
            </div>
          ))}

          {(ext.procedures || []).map((pr, i) => (
            <p key={i} style={{ margin: '6px 0', fontSize: 13.5 }}>
              <b>Procedure:</b> {pr.text}{' '}
              <span className={`code-chip ${pr.coding_confidence < 0.85 ? 'warn' : ''}`}>
                {pr.snomed_code || '—'}
              </span>{' '}
              {pr.coding_confidence != null && (
                <span className={pr.coding_confidence < 0.85 ? 'conf' : 'conf'}
                  style={{ color: pr.coding_confidence < 0.85 ? 'var(--amber)' : 'var(--teal)' }}>
                  {Math.round(pr.coding_confidence * 100)}%
                </span>
              )}
            </p>
          ))}

          <h2>Bill</h2>
          <p style={{ fontSize: 13.5 }}>
            {(b.line_items || []).length} items · grand total{' '}
            <b className="mono">{inr(b.grand_total)}</b>
          </p>

          {report && (
            <div className="checks">
              {flagged.length === 0 ? (
                <div className="row"><span className="mark">✅</span>
                  All {report.checks.length} checks passed — ready to approve.</div>
              ) : flagged.map((c, i) => (
                <div className="row" key={i}>
                  <span className="mark">{c.result === 'FAIL' ? '🔴' : '🟠'}</span>
                  <span><b>{c.code}</b> {c.check}{c.detail ? ` — ${c.detail}` : ''}</span>
                </div>
              ))}
              <details>
                <summary>All {report.checks.length} checks</summary>
                {report.checks.map((c, i) => (
                  <div className="row" key={i}>
                    <span className="mark">
                      {c.result === 'PASS' ? '✅' : c.result === 'FAIL' ? '🔴' : '🟠'}
                    </span>
                    <span>{c.code} {c.check}</span>
                  </div>
                ))}
              </details>
            </div>
          )}

          <div className="actions">
            <button className="btn ghost" disabled={busy} onClick={save}>
              Save edits and re-validate
            </button>
            <button className="btn primary" onClick={approve}
              disabled={busy || detail.approved || !report || report.status === 'FAIL'}>
              {detail.approved ? 'Approved ✓' : 'Approve and build FHIR bundle'}
            </button>
            {detail.approved && (
              <a className="btn ghost" href={api.bundleUrl(detail.id)}>Download bundle</a>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
