// Shared formatting + status helpers so every screen renders claims the same way.

export const inr = (n) =>
  n == null || n === '' ? '—' : `₹${Number(n).toLocaleString('en-IN')}`

// Backend statuses (api.py): APPROVED (bundle built), or validator status
// PASS / REVIEW / FAIL / DRAFT. We map each to a pill class + human label.
const STATUS = {
  APPROVED: { cls: 'APPROVED', label: 'APPROVED' },
  PASS: { cls: 'PASS', label: 'READY' },
  REVIEW: { cls: 'REVIEW', label: 'NEEDS REVIEW' },
  FAIL: { cls: 'FAIL', label: 'FAILED' },
  DRAFT: { cls: 'DRAFT', label: 'DRAFT' },
}

export const statusMeta = (status) =>
  STATUS[status] || { cls: 'DRAFT', label: status || 'DRAFT' }
