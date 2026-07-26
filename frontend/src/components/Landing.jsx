import React from 'react'

/* Landing page — mirrors Landing.dc.html. The hero animates a messy scan
   becoming a coded, approved claim (the product thesis, shown not told).
   Stat numbers are the real benchmark figures; the footnote names the
   benchmark's scope, per CLAUDE.md (never claim beyond what evaluate.py printed). */

const SCAN_LINES = ['88%', '64%', '76%', '40%', '80%', '55%']

const Shield = (p) => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--ink)" strokeWidth="1.75" {...p}>
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1Z" />
    <path d="m9 12 2 2 4-4" />
  </svg>
)

export default function Landing({ onSignIn }) {
  return (
    <div>
      <div className="land-top">
        <div className="brand">
          <span className="brand-mark">CB</span>
          <span className="brand-word">ClaimBridge</span>
        </div>
        <nav className="land-nav">
          <a href="#how">How it works</a>
          <a href="#proof">Accuracy</a>
          <button className="link" onClick={onSignIn}>Log in</button>
          <button className="btn primary" onClick={onSignIn}>Request a demo</button>
        </nav>
      </div>

      <div className="hero">
        <div>
          <div className="eyebrow">
            <span className="dot" />
            <span>BUILT FOR NHCX SUBMISSION</span>
          </div>
          <h1>Messy hospital paperwork.<br />Clean, submittable claims.</h1>
          <p className="hero-lead">
            ClaimBridge reads scanned discharge cards, bills and prescriptions —
            however faded, stapled or handwritten — and produces a coded,
            NHCX-format claim your clerks can approve in minutes, not days.
          </p>
          <div className="hero-cta">
            <button className="btn primary lg" onClick={onSignIn}>Request a demo</button>
            <a href="#how" className="btn ghost lg">See it work</a>
          </div>
          <div className="hero-stats">
            <div><div className="n">100%</div><div className="l">field accuracy on labelled benchmark*</div></div>
            <div><div className="n">~20s</div><div className="l">per claim vs 45–90 min manual*</div></div>
            <div><div className="n">20+</div><div className="l">validation rules applied</div></div>
          </div>
        </div>

        <div className="hero-anim" aria-hidden="true">
          <div className="doc-in">
            <div className="doc-stack">
              <div className="eyb">SCANNED · DISCHARGE CARD</div>
              <div className="doc-lines">
                {SCAN_LINES.map((w, i) => <div key={i} style={{ width: w }} />)}
              </div>
              <div className="doc-flag">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                  <path d="M12 9v4" /><path d="M12 17h.01" />
                </svg>
                <span>OCR ambiguous</span>
              </div>
            </div>
          </div>

          <div className="hero-engine">
            <div className="core">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--ink)" strokeWidth="2">
                <path d="M5 12h14" /><path d="m12 5 7 7-7 7" />
              </svg>
            </div>
          </div>

          <div className="claim-out">
            <div className="top">
              <span className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>CB-2291048</span>
              <span className="pill APPROVED">APPROVED</span>
            </div>
            <div className="who">Rahul Kumar · UHID <span className="mono" style={{ color: 'var(--ink)' }}>LC133326</span></div>
            <div className="cc-row"><span>Diagnosis (ICD-10)</span>
              <span className="cc-val">K35.80 <span className="conf-chip good">97%</span></span></div>
            <div className="cc-row"><span>Procedure (SNOMED)</span>
              <span className="cc-val">174041007 <span className="conf-chip good">96%</span></span></div>
            <div className="cc-row"><span>Claim amount</span>
              <span className="cc-val">₹74,323 <span className="conf-chip good">99%</span></span></div>
          </div>
        </div>
      </div>

      <div id="how" className="band">
        <div className="band-inner">
          <div className="head">
            <div className="band-kicker">HOW IT WORKS</div>
            <h2>Three steps from stack of paper to submitted claim</h2>
          </div>
          <div className="steps">
            <div className="step">
              <div className="step-n">01</div>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--ink)" strokeWidth="1.75">
                <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" /><path d="M12 12v9" /><path d="m16 16-4-4-4 4" />
              </svg>
              <div className="step-k">Upload</div>
              <p>Drop in scanned discharge cards, bills and prescriptions in any
                condition — photographed, faxed, or faded carbon copies.</p>
            </div>
            <div className="step">
              <div className="step-n">02</div>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--ink)" strokeWidth="1.75">
                <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" />
                <path d="M10 9H8" /><path d="M16 13H8" /><path d="M16 17H8" />
              </svg>
              <div className="step-k">Review</div>
              <p>Every extracted field carries its AI confidence. Anything under
                85% is flagged for a clerk to confirm — nothing ambiguous slips
                through silently.</p>
            </div>
            <div className="step">
              <div className="step-n">03</div>
              <Shield />
              <div className="step-k">Approve</div>
              <p>One click builds a validated FHIR bundle in NHCX format and
                submits it — with a full audit trail back to the original scan.</p>
            </div>
          </div>
        </div>
      </div>

      <div id="proof" className="band dark">
        <div className="band-inner">
          <div className="head">
            <div className="band-kicker">ACCURACY &amp; PROOF</div>
            <h2>Measured against a labelled benchmark, not a demo dataset</h2>
            <p className="band-lead">
              Graded field-by-field against manually labelled ground truth —
              clean documents and degraded scans alike.
            </p>
          </div>
          <div className="proof">
            <div className="proof-item"><div className="proof-n">100%</div><p>field accuracy on labelled benchmark</p></div>
            <div className="proof-item"><div className="proof-n">~20s</div><p>average processing time per claim</p></div>
            <div className="proof-item"><div className="proof-n">45–90m</div><p>manual equivalent, per claim</p></div>
            <div className="proof-item"><div className="proof-n">20+</div><p>validation rules run on every claim</p></div>
          </div>
          <div className="proof-note">
            *Benchmark: 8 synthetic patients, 30 documents (clean + degraded
            scans), 4 Indian hospital layouts, graded field-by-field against
            labelled ground truth. Results on your own document mix will vary.
          </div>
        </div>
      </div>

      <footer className="land-foot">
        <div className="land-foot-top">
          <div className="land-foot-brand">
            <div className="brand">
              <span className="brand-mark">CB</span>
              <span className="brand-word">ClaimBridge</span>
            </div>
            <p>AI that converts messy hospital documents into government-format
              insurance claims, built for the National Health Claims Exchange.</p>
          </div>
          <div className="land-foot-col">
            <h4>PRODUCT</h4>
            <a href="#how">How it works</a>
            <a href="#proof">Accuracy</a>
            <button className="link" onClick={onSignIn}>Log in</button>
          </div>
          <div className="land-foot-col">
            <h4>COMPANY</h4>
            <a href="#">About</a><a href="#">Security</a><a href="#">Contact</a>
          </div>
          <div className="land-foot-col">
            <h4>COMPLIANCE</h4>
            <a href="#">NHCX guide</a><a href="#">Data policy</a>
          </div>
        </div>
        <div className="land-foot-bottom">© 2026 ClaimBridge. Built for Indian hospitals.</div>
      </footer>
    </div>
  )
}
