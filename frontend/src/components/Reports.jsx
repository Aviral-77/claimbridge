import React from 'react'

/* Reports — analytics screen from Reports.dc.html. There is no reporting
   endpoint yet, so these are ILLUSTRATIVE operational figures (labelled as
   such) for the pitch/demo narrative — not measured output. When a reporting
   API lands, swap the constants below for a fetch. */

const INSURERS = [
  { name: 'Star Health', claims: 118, rejection: '2.5%', days: 9 },
  { name: 'HDFC Ergo', claims: 96, rejection: '3.1%', days: 12 },
  { name: 'ICICI Lombard', claims: 74, rejection: '4.0%', days: 13 },
  { name: 'Bajaj Allianz', claims: 53, rejection: '4.8%', days: 15 },
]
const REASONS = [
  { label: 'Diagnosis–procedure code mismatch', count: 14 },
  { label: 'Missing itemized bill', count: 9 },
  { label: 'Pre-authorization not on file', count: 6 },
  { label: 'Policy exclusion', count: 4 },
]

const Caret = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
)

const INS_GRID = { gridTemplateColumns: '2fr 1fr 1fr 1.2fr' }

export default function Reports() {
  return (
    <div className="page mid">
      <div className="reports-head">
        <div>
          <h1 className="page-title">Reports</h1>
          <div className="page-sub">Q2 FY2026 · 1 Apr – 21 Jul 2026</div>
        </div>
        <div className="reports-controls">
          <div className="select-box">This quarter <Caret /></div>
          <button className="btn ghost">Export</button>
        </div>
      </div>

      <div className="metrics">
        <div className="metric">
          <div className="label">Rejection rate</div>
          <div className="value">3.2%</div>
          <div className="delta">vs 14.6% before ClaimBridge</div>
        </div>
        <div className="metric">
          <div className="label">Avg. days to payment</div>
          <div className="value">11</div>
          <div className="delta">vs 34 days before</div>
        </div>
        <div className="metric">
          <div className="label">Claim value recovered</div>
          <div className="value teal">₹21.4L</div>
          <div className="delta">previously rejected, won on appeal</div>
        </div>
        <div className="metric">
          <div className="label">Staff-hours saved</div>
          <div className="value">612</div>
          <div className="delta">vs manual claim preparation</div>
        </div>
      </div>

      <div className="report-block">
        <h3>Rejection rate over time</h3>
        <div className="sub">Monthly, since onboarding</div>
        <svg width="100%" height="220" viewBox="0 0 900 220" preserveAspectRatio="none">
          {[20, 70, 120, 170].map((y) => (
            <line key={y} x1="0" y1={y} x2="900" y2={y} stroke="#EDEFF1" strokeWidth="1" />
          ))}
          <polyline className="chart-line" points="0,30 150,55 300,90 450,130 600,155 750,168 900,178"
            fill="none" stroke="var(--teal)" strokeWidth="2" />
          <g fontFamily="IBM Plex Mono" fontSize="11" fill="#8a97a4">
            <text x="0" y="14">14.6%</text>
            <text x="850" y="200">3.2%</text>
          </g>
        </svg>
        <div className="chart-x">
          {['Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'].map((m) => <span key={m}>{m}</span>)}
        </div>
      </div>

      <div className="report-block">
        <h3 style={{ marginBottom: 20 }}>By insurer</h3>
        <div className="rtable">
          <div className="rtable-head" style={INS_GRID}>
            <div className="col-h">INSURER</div>
            <div className="col-h t-right">CLAIMS</div>
            <div className="col-h t-right">REJECTION %</div>
            <div className="col-h t-right">AVG DAYS TO PAYMENT</div>
          </div>
          {INSURERS.map((ins) => (
            <div className="rtable-row" style={INS_GRID} key={ins.name}>
              <div className="cell-name">{ins.name}</div>
              <div className="cell-amt">{ins.claims}</div>
              <div className="cell-amt">{ins.rejection}</div>
              <div className="cell-amt">{ins.days}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="report-block">
        <h3 style={{ marginBottom: 20 }}>Top rejection reasons</h3>
        <div className="rtable">
          {REASONS.map((r) => (
            <div className="rtable-row" style={{ gridTemplateColumns: '1fr auto' }} key={r.label}>
              <div className="cell-name">{r.label}</div>
              <div className="cell-amt cell-muted">{r.count}</div>
            </div>
          ))}
        </div>
        <div className="report-note">
          Figures on this page are illustrative operational estimates for the
          pilot narrative — not measured engine output. Extraction accuracy is
          reported separately against the labelled benchmark.
        </div>
      </div>
    </div>
  )
}
