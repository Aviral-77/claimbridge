import React, { useEffect, useState } from 'react'

/* ProcessingStepper — from ProcessingStepper.dc.html, but driven by the REAL
   pipeline call instead of a scripted timer. The engine runs as one ~20s
   request (extract → code → validate), so we advance the first steps on a
   timer for feedback and let the actual API result resolve the final state:
     phase 'running' → animate up to "Running validation" and hold
     phase 'done'    → all steps complete; "Open review" CTA (amber if REVIEW)
     phase 'failed'  → mark the active step failed; offer Retry            */

const STEPS = [
  { label: 'Reading documents', active: 'Reading documents…' },
  { label: 'Extracting fields', active: 'Extracting patient, dates, bill items…' },
  { label: 'Assigning medical codes', active: 'Matching ICD-10 / SNOMED candidates…' },
  { label: 'Running validation', active: 'Running 20+ checks…' },
  { label: 'Ready for review', active: 'Finalizing draft bundle…' },
]

const Check = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3"><path d="m5 12 5 5L20 7" /></svg>
)
const Cross = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
)

export default function ProcessingStepper({ claimId, phase, result, error, onOpenReview, onRetry }) {
  const [active, setActive] = useState(0)

  // Advance through the first four steps while the request is in flight.
  useEffect(() => {
    if (phase !== 'running') return
    setActive(0)
    const timers = [900, 5000, 10000].map((ms, i) =>
      setTimeout(() => setActive(i + 1), ms))
    const hold = setTimeout(() => setActive(3), 14000) // hold on validation
    return () => { timers.forEach(clearTimeout); clearTimeout(hold) }
  }, [phase])

  const done = phase === 'done'
  const failed = phase === 'failed'
  const needsReview = done && result?.status === 'REVIEW'
  const failedStatus = done && result?.status === 'FAIL'

  const stateOf = (i) => {
    if (failed) {
      if (i < active) return 'done'
      if (i === active) return 'failed'
      return 'pending'
    }
    if (done) {
      if (i === 3 && (needsReview || failedStatus)) return 'attention'
      return 'done'
    }
    if (i < active) return 'done'
    if (i === active) return 'active'
    return 'pending'
  }

  const detailOf = (i, st) => {
    if (st === 'pending' || (failed && i > active)) return ''
    if (st === 'failed') return error || 'Processing failed. Check the API server and LLM key, then retry.'
    if (done) {
      if (i === 3) {
        if (failedStatus) return 'Validation found blocking errors — open to fix'
        if (needsReview) return 'Some fields need your confirmation'
        return 'All checks passed'
      }
      if (i === 4) return `Draft bundle assembled${result?.seconds ? ` · ${result.seconds}s` : ''}`
      return STEPS[i].active.replace('…', ' · done')
    }
    return STEPS[i].active
  }

  return (
    <div className="stepper">
      <div className="stepper-head">
        <div>
          <div className="k">PROCESSING CLAIM</div>
          <div className="id">{claimId}</div>
        </div>
      </div>

      <div>
        {STEPS.map((s, i) => {
          const st = stateOf(i)
          const isLast = i === STEPS.length - 1
          const rowOpacity = failed && i > active ? 0.4 : (st === 'done' ? 0.72 : 1)
          const lineFilled = st === 'done' || st === 'attention'
          const lineColor = st === 'attention' ? 'var(--amber)' : 'var(--teal)'
          const labelColor = st === 'pending' ? 'var(--muted-2)'
            : st === 'failed' ? 'var(--red)' : 'var(--ink)'
          const detailColor = st === 'failed' ? 'var(--red)'
            : st === 'attention' ? 'var(--amber)'
            : st === 'active' ? 'var(--ink)' : 'var(--muted)'

          return (
            <div key={i} className="step-row" style={{ opacity: rowOpacity }}>
              <div className="step-rail">
                <div className={`step-dot ${st}`}>
                  {st === 'done' && <Check />}
                  {st === 'attention' && <span style={{ color: '#fff', fontFamily: 'var(--mono)', fontWeight: 700, fontSize: 13 }}>!</span>}
                  {st === 'failed' && <Cross />}
                  {(st === 'pending' || st === 'active') && <span className="inner" />}
                </div>
                {!isLast && (
                  <div className="step-line">
                    <div style={{ height: lineFilled ? '100%' : '0', background: lineColor }} />
                  </div>
                )}
              </div>
              <div className="step-body">
                <div className="step-label" style={{ color: labelColor }}>{s.label}</div>
                <div className="step-detail" style={{ color: detailColor }}>{detailOf(i, st)}</div>

                {failed && st === 'failed' && (
                  <button className="btn danger sm" style={{ marginTop: 12 }} onClick={onRetry}>Retry</button>
                )}
                {done && isLast && (
                  <button className="btn primary" style={{ marginTop: 10 }} onClick={onOpenReview}>
                    Open review
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M5 12h14" /><path d="m12 5 7 7-7 7" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
