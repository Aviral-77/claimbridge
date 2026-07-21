// Thin client for the ClaimBridge API (FastAPI on :8000, proxied via Vite).

async function j(res) {
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch {}
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  listClaims: () => fetch('/api/claims').then(j),
  getClaim: (id) => fetch(`/api/claims/${id}`).then(j),
  createClaim: (id, files) => {
    const fd = new FormData()
    fd.append('claim_id', id)
    files.forEach((f) => fd.append('files', f))
    return fetch('/api/claims', { method: 'POST', body: fd }).then(j)
  },
  updateClaim: (id, extraction) =>
    fetch(`/api/claims/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(extraction),
    }).then(j),
  approve: (id) => fetch(`/api/claims/${id}/approve`, { method: 'POST' }).then(j),
  bundleUrl: (id) => `/api/claims/${id}/bundle`,
  previewUrl: (id, name, page = 0) =>
    `/api/claims/${id}/documents/${encodeURIComponent(name)}/preview?page=${page}`,
}
