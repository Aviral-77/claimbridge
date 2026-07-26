import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import ProcessingStepper from './ProcessingStepper.jsx'

/* Upload — from Upload.dc.html. Uploads files, then the API returns 202
   immediately (A5) and this component POLLS GET /api/claims/{id}/status (A6)
   until the claim reaches a terminal state, driving the live ProcessingStepper. */

const stamp = () => {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `CLM-${String(d.getFullYear()).slice(2)}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`
}

const sizeOf = (b) => (b > 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${(b / 1024).toFixed(0)} KB`)

const TERMINAL = ['PASS', 'REVIEW', 'FAIL', 'APPROVED']
const POLL_MS = 2000

const FileIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="1.75">
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" />
  </svg>
)

export default function UploadFlow({ say, onOpenReview, onCancel }) {
  const [claimId, setClaimId] = useState(stamp())
  const [files, setFiles] = useState([])
  const [armed, setArmed] = useState(false)
  const [phase, setPhase] = useState('idle')   // idle | running | done | failed
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const inputRef = useRef()
  const pollRef = useRef(null)

  // Stop polling if the user navigates away mid-process.
  useEffect(() => () => clearTimeout(pollRef.current), [])

  const addFiles = (list) => {
    const ok = [...list].filter((f) => /\.(pdf|png|jpe?g)$/i.test(f.name))
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name))
      return [...prev, ...ok.filter((f) => !names.has(f.name))]
    })
  }

  const removeFile = (name) => setFiles((prev) => prev.filter((f) => f.name !== name))

  const poll = (id) => {
    let misses = 0
    const tick = async () => {
      try {
        const s = await api.claimStatus(id)
        if (!TERMINAL.includes(s.status)) {          // QUEUED / RUNNING → keep waiting
          pollRef.current = setTimeout(tick, POLL_MS)
          return
        }
        if (s.status === 'FAIL' && s.error) {        // the worker crashed
          setError(s.error)
          setPhase('failed')
        } else {                                     // PASS / REVIEW / FAIL(validation)
          setResult({ id, status: s.status, seconds: s.seconds })
          setPhase('done')
          say(`Processed${s.seconds ? ` in ${s.seconds}s` : ''} — ${s.status}`)
        }
      } catch (e) {
        if (++misses > 5) {                          // give up after ~10s of errors
          setError(String(e.message || e))
          setPhase('failed')
          return
        }
        pollRef.current = setTimeout(tick, POLL_MS)
      }
    }
    tick()
  }

  const process = async () => {
    clearTimeout(pollRef.current)
    setPhase('running')
    setError(null)
    setResult(null)
    try {
      const res = await api.createClaim(claimId.trim(), files)  // returns 202 immediately
      poll(res.id)
    } catch (e) {
      setError(String(e.message || e))
      setPhase('failed')
    }
  }

  const running = phase === 'running' || phase === 'done' || phase === 'failed'

  return (
    <div className="page narrow">
      <h1 className="page-title">Upload documents</h1>
      <div className="page-sub" style={{ marginBottom: 32, maxWidth: 640 }}>
        Add every document for this claim — discharge card, itemized bill, and
        prescriptions. ClaimBridge reads them together as one patient's claim.
      </div>

      {!running && (
        <>
          <div className="field" style={{ maxWidth: 420 }}>
            <label htmlFor="cid">Claim reference</label>
            <input id="cid" className="input" value={claimId}
              onChange={(e) => setClaimId(e.target.value)} />
          </div>

          <div
            className={`drop ${armed ? 'armed' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setArmed(true) }}
            onDragLeave={() => setArmed(false)}
            onDrop={(e) => { e.preventDefault(); setArmed(false); addFiles(e.dataTransfer.files) }}
          >
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--ink)" strokeWidth="1.5" style={{ margin: '0 auto' }}>
              <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" /><path d="M12 12v9" /><path d="m16 16-4-4-4 4" />
            </svg>
            <div className="big">Drag files here, or browse</div>
            <div className="hint">Supports PDF, JPG and PNG · read together as one claim</div>
            <button className="btn dark" onClick={() => inputRef.current.click()}>Browse files</button>
            <input ref={inputRef} type="file" multiple hidden accept=".pdf,.png,.jpg,.jpeg"
              onChange={(e) => addFiles(e.target.files)} />
          </div>
        </>
      )}

      {files.length > 0 && (
        <>
          <div className="filelabel">{files.length} FILE{files.length > 1 ? 'S' : ''} · CLAIM {claimId}</div>
          <div className="filelist">
            {files.map((f) => (
              <div className="file-row" key={f.name}>
                <FileIcon />
                <div className="fmeta">
                  <div className="name">{f.name}</div>
                  <div className="file-bar"><div style={{ width: '100%' }} /></div>
                </div>
                <div className="file-size">{sizeOf(f.size)}</div>
                {running ? (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--teal)" strokeWidth="2">
                    <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10Z" /><path d="m9 12 2 2 4-4" />
                  </svg>
                ) : (
                  <button className="file-x" aria-label={`Remove ${f.name}`} onClick={() => removeFile(f.name)}>×</button>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {running && (
        <ProcessingStepper
          claimId={claimId}
          phase={phase}
          result={result}
          error={error}
          onOpenReview={() => onOpenReview(result.id)}
          onRetry={process}
        />
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 16, marginTop: 24 }}>
        {!running ? (
          <>
            <button className="btn ghost" onClick={onCancel}>Cancel</button>
            <button className="btn primary" disabled={!files.length || !claimId.trim()} onClick={process}>
              Process {files.length} document{files.length !== 1 ? 's' : ''}
            </button>
          </>
        ) : (
          <button className="btn ghost" onClick={onCancel}>Back to dashboard</button>
        )}
      </div>
    </div>
  )
}
