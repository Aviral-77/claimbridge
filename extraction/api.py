#!/usr/bin/env python3
"""ClaimBridge API — FastAPI backend for the React frontend.

Run (from the extraction/ folder):
  pip install -r requirements.txt
  alembic upgrade head
  uvicorn api:app --reload --port 8000
  celery -A tasks.celery_app worker --loglevel=info   # separate process

Phase A2: state in a database (Postgres).
Phase A3: document bytes in S3/MinIO (no more app_data/uploads on disk).
Phase A4: processing runs on a Celery worker (the API delegates to it).
The API still waits for the result here — Phase A5 makes that non-blocking (202).
"""

import base64
import io
import json
import os
import sys
from typing import List

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from db import get_db, init_db          # noqa: E402
from logging_setup import get_logger    # noqa: E402
from models import Claim, Document       # noqa: E402

log = get_logger("api")
jobs = get_logger("jobs")     # shared job-lifecycle log (logs/jobs.log)

app = FastAPI(title="ClaimBridge API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.on_event("startup")
def _startup():
    log.info("API starting up")
    init_db()
    try:
        import storage
        storage.ensure_bucket()
    except Exception as e:
        log.warning("bucket ensure skipped: %s", e)
    log.info("startup complete")


# --- demo auth -------------------------------------------------------------
# Demo-grade: fixed users, opaque token. Real identity (JWT, hashed passwords,
# multi-tenancy) is Phase A7.
DEMO_USERS = {
    "desk@skn.hospital": {"password": "claims123",
                          "name": "Claims Desk",
                          "org": "Shree Krishna Nursing Home"},
    "admin@lifecare.in": {"password": "claims123",
                          "name": "Admin",
                          "org": "LifeCare Multispeciality Hospital"},
}
_TOKENS = {}


@app.post("/api/login")
def login(body: dict):
    email = (body.get("email") or "").strip().lower()
    user = DEMO_USERS.get(email)
    if not user or user["password"] != (body.get("password") or ""):
        log.warning("login failed for %r", email)
        raise HTTPException(401, "Email or password is incorrect")
    token = base64.urlsafe_b64encode(os.urandom(24)).decode()
    _TOKENS[token] = email
    log.info("login ok: %s (%s)", email, user["org"])
    return {"token": token, "name": user["name"], "org": user["org"],
            "email": email}


@app.post("/api/logout")
def logout(body: dict):
    removed = _TOKENS.pop(body.get("token"), None)
    log.info("logout: %s", removed or "(unknown token)")
    return {"ok": True}


# --- claims ----------------------------------------------------------------
@app.get("/api/claims")
def list_claims(db: Session = Depends(get_db)):
    claims = db.execute(
        select(Claim).order_by(Claim.updated_at.desc())).scalars().all()
    log.info("list_claims -> %d claim(s)", len(claims))
    return [c.summary() for c in claims]


@app.get("/api/claims/{cid}")
def get_claim(cid: str, db: Session = Depends(get_db)):
    claim = db.get(Claim, cid)
    if not claim:
        log.warning("get_claim: %s not found", cid)
        raise HTTPException(404, "claim not found")
    log.info("get_claim: %s (status=%s, docs=%d)",
             cid, claim.status, len(claim.documents))
    return {
        "id": claim.id,
        "extraction": claim.extraction,
        "validation": claim.validation,
        "documents": [d.filename for d in claim.documents],
        "approved": claim.approved,
        "status": "APPROVED" if claim.approved else claim.status,
    }


@app.post("/api/claims", status_code=202)
async def create_claim(claim_id: str = Form(...),
                       files: List[UploadFile] = File(...),
                       db: Session = Depends(get_db)):
    """Accept the upload, enqueue processing, and return 202 immediately. The
    client polls GET /api/claims/{id}/status for progress (A6)."""
    import storage
    from tasks import process_claim

    cid = claim_id.strip()
    log.info("create_claim: %s (%d file(s))", cid, len(files))

    # 1) Upload document bytes to object storage; record metadata.
    docs = []
    for uf in files:
        blob = await uf.read()
        key = storage.document_key(cid, uf.filename)
        storage.put_bytes(key, blob, uf.content_type)
        docs.append(Document(filename=uf.filename, content_type=uf.content_type,
                             storage_key=key, size_bytes=len(blob)))

    # 2) Create/replace the claim row as QUEUED.
    claim = db.get(Claim, cid) or Claim(id=cid)
    claim.status = "QUEUED"
    claim.approved = False
    claim.extraction = {}
    claim.validation = None
    claim.bundle = None
    claim.error = None
    claim.seconds = None
    claim.patient_name = claim.uhid = None
    claim.amount = None
    claim.flags = 0
    claim.documents = docs
    db.add(claim)
    db.commit()

    # 3) Hand off to the worker and return right away — the API is now free.
    async_result = process_claim.delay(cid)
    claim.task_id = async_result.id
    claim.stage = "queued"
    db.commit()
    log.info("[%s] QUEUED — task %s", cid, async_result.id)
    jobs.info("task=%s claim=%s stage=queued", async_result.id, cid)
    return {"id": cid, "status": "QUEUED", "task_id": async_result.id}


@app.get("/api/claims/{cid}/status")
def claim_status(cid: str, db: Session = Depends(get_db)):
    """Lightweight polling endpoint — status + live stage, no heavy payload."""
    claim = db.get(Claim, cid)
    if not claim:
        raise HTTPException(404, "claim not found")
    log.debug("status: %s -> %s (%s)", cid, claim.status, claim.stage)
    return {
        "id": cid,
        "status": "APPROVED" if claim.approved else claim.status,
        "stage": claim.stage,
        "task_id": claim.task_id,
        "seconds": claim.seconds,
        "flags": claim.flags or 0,
        "error": claim.error,
    }


# --- task tracking ---------------------------------------------------------
@app.get("/api/tasks")
def list_tasks(db: Session = Depends(get_db)):
    """All processing jobs (claims that have been enqueued), newest first."""
    claims = db.execute(
        select(Claim).where(Claim.task_id.isnot(None))
        .order_by(Claim.updated_at.desc())).scalars().all()
    log.info("list_tasks -> %d job(s)", len(claims))
    return [c.job() for c in claims]


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    """Track one job by its Celery task id: DB status/stage + live Celery state."""
    claim = db.execute(
        select(Claim).where(Claim.task_id == task_id)).scalar_one_or_none()
    if not claim:
        log.warning("get_task: %s not found", task_id)
        raise HTTPException(404, "task not found")
    view = claim.job()
    try:                                   # best-effort — backend may have expired
        from tasks import celery_app
        view["celery_state"] = celery_app.AsyncResult(task_id).state
    except Exception:
        view["celery_state"] = None
    log.info("get_task: %s stage=%s status=%s", task_id, claim.stage, claim.status)
    return view


@app.put("/api/claims/{cid}")
def update_claim(cid: str, ext: dict, db: Session = Depends(get_db)):
    from validator import validate

    claim = db.get(Claim, cid)
    if not claim:
        log.warning("update_claim: %s not found", cid)
        raise HTTPException(404, "claim not found")
    report = validate(ext)
    patient = (ext.get("patient") or {}).get("name")
    uhid = (ext.get("patient") or {}).get("uhid")
    amount = (ext.get("billing") or {}).get("grand_total")
    flags = (report or {}).get("summary", {}).get("review_flags", 0)
    claim.extraction = ext
    claim.validation = report
    claim.status = report["status"]
    claim.patient_name, claim.uhid, claim.amount, claim.flags = patient, uhid, amount, flags
    db.commit()
    log.info("update_claim: %s re-validated -> %s", cid, report["status"])
    return {"id": cid, "status": report["status"], "validation": report}


@app.post("/api/claims/{cid}/approve")
def approve(cid: str, db: Session = Depends(get_db)):
    from fhir_builder import build_bundle

    claim = db.get(Claim, cid)
    if not claim:
        log.warning("approve: %s not found", cid)
        raise HTTPException(404, "claim not found")
    if not claim.validation or claim.validation["status"] == "FAIL":
        log.warning("approve blocked: %s has failing checks", cid)
        raise HTTPException(409, "claim has failing checks — fix before approving")
    bundle = build_bundle(claim.extraction)
    claim.bundle = json.loads(bundle.model_dump_json())
    claim.approved = True
    db.commit()
    log.info("approve: %s — FHIR bundle built", cid)
    return {"id": cid, "approved": True}


@app.get("/api/claims/{cid}/bundle")
def download_bundle(cid: str, db: Session = Depends(get_db)):
    claim = db.get(Claim, cid)
    if not claim or not claim.bundle:
        log.warning("bundle download: %s has no bundle", cid)
        raise HTTPException(404, "no bundle — approve the claim first")
    log.info("bundle download: %s", cid)
    return Response(json.dumps(claim.bundle, indent=2),
                    media_type="application/fhir+json",
                    headers={"Content-Disposition":
                             f'attachment; filename="{cid}_bundle.json"'})


@app.get("/api/claims/{cid}/documents/{name}/preview")
def doc_preview(cid: str, name: str, page: int = 0, db: Session = Depends(get_db)):
    """PNG render of a page (poppler), or {'text': ...} fallback. Bytes come from
    object storage now — no filesystem, and no path-traversal surface (we look
    the document up by claim + filename in the DB)."""
    import storage

    doc = db.execute(
        select(Document).where(Document.claim_id == cid,
                               Document.filename == name)).scalar_one_or_none()
    if not doc or not doc.storage_key:
        log.warning("doc_preview: %s/%s not found", cid, name)
        raise HTTPException(404, "document not found")
    log.info("doc_preview: %s/%s page=%d", cid, name, page)
    blob = storage.get_bytes(doc.storage_key)

    if name.lower().endswith((".png", ".jpg", ".jpeg")):
        return Response(blob, media_type="image/png")
    try:
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(blob, dpi=110,
                                   first_page=page + 1, last_page=page + 1)
        buf = io.BytesIO()
        pages[0].save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png")
    except Exception:
        log.info("doc_preview: %s/%s — falling back to text layer", cid, name)
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "")
                         for p in PdfReader(io.BytesIO(blob)).pages)
        return JSONResponse({"text": text})
