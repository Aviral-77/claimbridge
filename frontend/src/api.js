// Thin client for the ClaimBridge API (FastAPI on :8000, proxied via Vite).
// A7: every call carries the JWT from the saved session; media URLs (img/href,
// which can't send an Authorization header) pass it as ?token=.

const SESSION_KEY = 'claimbridge.session'

function authToken() {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || '{}').token || '' }
  catch { return '' }
}

// Build headers with the bearer token (plus any extras, e.g. Content-Type).
function h(extra = {}) {
  const t = authToken()
  return t ? { ...extra, Authorization: `Bearer ${t}` } : extra
}

async function j(res) {
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch {}
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  listClaims: () => fetch('/api/claims', { headers: h() }).then(j),
  getClaim: (id) => fetch(`/api/claims/${id}`, { headers: h() }).then(j),
  createClaim: (id, files) => {
    const fd = new FormData()
    fd.append('claim_id', id)
    files.forEach((f) => fd.append('files', f))
    // No Content-Type — the browser sets the multipart boundary itself.
    return fetch('/api/claims', { method: 'POST', headers: h(), body: fd }).then(j)
  },
  claimStatus: (id) => fetch(`/api/claims/${id}/status`, { headers: h() }).then(j),
  updateClaim: (id, extraction) =>
    fetch(`/api/claims/${id}`, {
      method: 'PUT',
      headers: h({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(extraction),
    }).then(j),
  approve: (id) =>
    fetch(`/api/claims/${id}/approve`, { method: 'POST', headers: h() }).then(j),
  bundleUrl: (id) =>
    `/api/claims/${id}/bundle?token=${encodeURIComponent(authToken())}`,
  previewUrl: (id, name, page = 0) =>
    `/api/claims/${id}/documents/${encodeURIComponent(name)}/preview` +
    `?page=${page}&token=${encodeURIComponent(authToken())}`,
}
