import React, { useRef, useState } from 'react'
import { api } from '../api.js'

const stamp = () => {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `CLM-${String(d.getFullYear()).slice(2)}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`
}

export default function UploadFlow({ onDone, say }) {
  const [claimId, setClaimId] = useState(stamp())
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [armed, setArmed] = useState(false)
  const inputRef = useRef()

  const addFiles = (list) => {
    const ok = [...list].filter((f) => /\.(pdf|png|jpe?g)$/i.test(f.name))
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name))
      return [...prev, ...ok.filter((f) => !names.has(f.name))]
    })
  }

  const process = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.createClaim(claimId.trim(), files)
      say(`Processed in ${res.seconds}s — validation: ${res.status}`)
      onDone(res.id)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1>Upload documents</h1>
      <p className="sub">
        Discharge summary, final bill, lab reports — PDFs, scans, or photos.
        The engine reads them together as one claim.
      </p>

      <div className="field" style={{ maxWidth: 420 }}>
        <label htmlFor="cid">Claim reference</label>
        <input id="cid" value={claimId} onChange={(e) => setClaimId(e.target.value)} />
      </div>

      <div
        className={`drop ${armed ? 'armed' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setArmed(true) }}
        onDragLeave={() => setArmed(false)}
        onDrop={(e) => { e.preventDefault(); setArmed(false); addFiles(e.dataTransfer.files) }}
      >
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
          stroke="#3E5065" strokeWidth="1.6" aria-hidden="true">
          <path d="M12 16V4m0 0L7 9m5-5l5 5" />
          <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
        </svg>
        <div className="big">Drag files here</div>
        <div className="hint">PDF, JPG or PNG · read together as one patient's claim</div>
        <button className="btn primary" onClick={() => inputRef.current.click()}>
          Choose files
        </button>
        <input ref={inputRef} type="file" multiple hidden
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={(e) => addFiles(e.target.files)} />
      </div>

      {files.length > 0 && (
        <div className="card filelist">
          {files.map((f) => (
            <div className="file-row" key={f.name}>
              <div className="file-badge">{f.name.split('.').pop().toUpperCase()}</div>
              <div>{f.name}
                <div className="muted">{(f.size / 1024).toFixed(0)} KB</div>
              </div>
              <div style={{ flex: 1 }} />
              <button className="btn ghost" style={{ padding: '5px 12px' }}
                onClick={() => setFiles(files.filter((x) => x.name !== f.name))}>
                Remove
              </button>
            </div>
          ))}
          <div style={{ padding: '13px 16px', borderTop: '1px solid var(--line)' }}>
            <button className="btn primary" disabled={busy || !claimId.trim()}
              onClick={process}>
              {busy ? 'Processing…' : `Process ${files.length} document${files.length > 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      )}

      {busy && (
        <div className="card progress">
          Reading documents, extracting fields, assigning medical codes,
          running validation… usually 20–30 seconds.
        </div>
      )}
      {error && (
        <div className="card progress" style={{ borderLeftColor: 'var(--red)' }}>
          Processing failed: {error}. Check that the API server is running and
          your LLM key is set, then try again.
        </div>
      )}
    </>
  )
}
