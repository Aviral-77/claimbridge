import React from 'react'

/* The hero's thesis: the product IS a transformation — a messy scan on the
   left becoming a coded, validated claim on the right. Shown, not told. */

const SCAN_LINES = [
  'SHREE KRISHNA NURSING HOME',
  'DISCHARGE CARD',
  'Name of Pateint : Meena Sharma  Age/Sex: 70/F',
  'D.O.A: 23/04/2026    D.O.D: 27/04/2026',
  'DIAGNOSIS :- Type 2 diabetes mellitus',
  'with hyperglycemia',
  'TREATMENT GIVEN :-',
  ' - Inj. Human Insulin (Actrapid)',
  ' - Tab. Metformin 500mg BD',
]

export default function Landing({ onSignIn }) {
  return (
    <div className="landing">
      <header className="land-top">
        <div className="logo dark"><span className="logo-dot" />ClaimBridge</div>
        <nav className="land-nav">
          <a href="#how">How it works</a>
          <a href="#proof">Accuracy</a>
          <button className="btn primary" onClick={onSignIn}>Sign in</button>
        </nav>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">For hospital claims desks · NHCX-ready</p>
          <h1 className="hero-h1">
            Messy hospital paperwork in.<br />
            <span className="hero-teal">Clean, coded claims out.</span>
          </h1>
          <p className="hero-sub">
            ClaimBridge reads discharge summaries, bills, and lab reports —
            even bad scans — and turns them into validated, government-format
            insurance claims. Your clerk reviews in minutes, not hours.
          </p>
          <div className="hero-cta">
            <button className="btn primary lg" onClick={onSignIn}>
              Open the console
            </button>
            <span className="hero-cred mono">demo: desk@skn.hospital / claims123</span>
          </div>
        </div>

        <div className="hero-visual" aria-hidden="true">
          <div className="scan">
            {SCAN_LINES.map((l, i) => (
              <div className="scan-line" key={i} style={{ animationDelay: `${i * 90}ms` }}>
                {l}
              </div>
            ))}
            <div className="scan-stamp">SCANNED · 120 dpi</div>
          </div>
          <div className="hero-arrow">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2">
              <path d="M5 12h14m0 0l-6-6m6 6l-6 6" />
            </svg>
          </div>
          <div className="claimcard">
            <div className="claimcard-title">Extracted claim</div>
            <div className="cc-row"><span>Patient</span><b>Meena Sharma · 70 F</b></div>
            <div className="cc-row"><span>Stay</span>
              <b className="mono">23 Apr → 27 Apr 2026</b></div>
            <div className="cc-row"><span>Diagnosis</span>
              <span><span className="code-chip mono">E11.65</span> <em className="conf-in">98%</em></span>
            </div>
            <div className="cc-row"><span>Claim total</span>
              <b className="mono">₹30,771</b></div>
            <div className="cc-checks">
              <div>✓ 18 of 18 validation checks passed</div>
              <div>✓ FHIR bundle ready for NHCX</div>
            </div>
          </div>
        </div>
      </section>

      <section className="band" id="how">
        <h2 className="band-h2">One desk. Three steps. No new hospital software.</h2>
        <div className="steps">
          <div className="step">
            <div className="step-k">Upload</div>
            <p>Drag in whatever the ward produced — typed PDFs, photocopies,
              phone photos. The engine reads them together as one claim.</p>
          </div>
          <div className="step">
            <div className="step-k">Review</div>
            <p>Every extracted field carries its own confidence score. Anything
              under 85% turns amber and waits for a human glance — nothing
              uncertain leaves the building unchecked.</p>
          </div>
          <div className="step">
            <div className="step-k">Approve</div>
            <p>One click runs 20+ validation rules, assembles the FHIR bundle,
              and readies the claim for the National Health Claims Exchange.</p>
          </div>
        </div>
      </section>

      <section className="band paper" id="proof">
        <h2 className="band-h2">Measured, not promised</h2>
        <div className="proof">
          <div className="proof-item">
            <div className="proof-n mono">100%</div>
            <p>field accuracy on our labelled benchmark — clean documents
              and degraded scans alike</p>
          </div>
          <div className="proof-item">
            <div className="proof-n mono">~20s</div>
            <p>per claim, versus 45–90 minutes of manual portal entry</p>
          </div>
          <div className="proof-item">
            <div className="proof-n mono">20+</div>
            <p>validation rules run before any claim can be approved —
              dates, totals, codes, consistency</p>
          </div>
        </div>
        <p className="proof-note">
          Benchmark: 8 synthetic patients, 30 documents, 4 hospital layouts,
          graded field-by-field against labelled ground truth. Ask us to run
          it in front of you.
        </p>
      </section>

      <footer className="land-foot">
        <div className="logo dark"><span className="logo-dot" />ClaimBridge</div>
        <span>Built for India's National Health Claims Exchange · ABDM-aligned</span>
      </footer>
    </div>
  )
}
