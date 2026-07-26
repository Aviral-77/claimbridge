#!/usr/bin/env python3
"""ClaimBridge API — FastAPI backend for the React frontend.

Run (from the extraction/ folder):
  pip install -r requirements.txt
  alembic upgrade head
  uvicorn api:app --reload --port 8000
  celery -A tasks.celery_app worker --loglevel=info   # separate process

Phase A2: state in Postgres.  A3: documents in S3/MinIO.  A4/A5: async on a
Celery worker (non-blocking API).  A6: frontend polls.  A7: JWT auth +
per-hospital multi-tenancy (every claim endpoint requires a bearer token and is
scoped to the caller's hospital).
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

from auth import (create_token, get_current_user, seed_demo,  # noqa: E402
                  user_from_query_token, verify_password)
from db import SessionLocal, get_db, init_db          # noqa: E402
from logging_setup import get_logger                   # noqa: E402
from models import Claim, Document, Hospital, User      # noqa: E402

log = get_logger("api")
jobs = get_logger("jobs")     # shared job-lifecycle log (logs/jobs.log)

app = FastAPI(title="ClaimBridge API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.on_event("startup")
def _startup():
    log.info("API starting up")
    init_db()
    db = SessionLocal()
    try:
        seed_demo(db)
    finally:
        db.close()
    try:
        import storage
        storage.ensure_bucket()
    except Exception as e:
        log.warning("bucket ensure skipped: %s", e)
    log.info("startup complete")


def _owned_or_404(claim: Claim | None, user: User) -> Claim:
    """404 (not 403) if the claim doesn't exist OR belongs to another hospital —
    don't reveal existence across tenants."""
    if not claim or claim.hospital_id != user.hospital_id:
        raise HTTPException(404, "claim not found")
    return claim


# --- auth ------------------------------------------------------------------
@app.post("/api/login")
def login(body: dict, db: Session = Depends(get_db)):
    email = (body.get("email") or "").strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(body.get("password") or "", user.password_hash):
        log.warning("login failed for %r", email)
        raise HTTPException(401, "Email or password is incorrect")
    hospital = db.get(Hospital, user.hospital_id)
    token = create_token(user)
    log.info("login ok: %s (%s)", email, user.hospital_id)
    return {"token": token, "name": user.name,
            "org": hospital.name if hospital else user.hospital_id,
            "email": user.email, "role": user.role}


@app.post("/api/logout")
def logout(body: dict):
    # Stateless JWT — logout is client-side (drop the token). No server state.
    return {"ok": True}


# --- claims ----------------------------------------------------------------
@app.get("/api/claims")
def list_claims(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    claims = db.execute(
        select(Claim).where(Claim.hospital_id == user.hospital_id)
        .order_by(Claim.updated_at.desc())).scalars().all()
    log.info("list_claims(%s) -> %d claim(s)", user.hospital_id, len(claims))
    return [c.summary() for c in claims]


@app.get("/api/claims/{cid}")
def get_claim(cid: str, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    claim = _owned_or_404(db.get(Claim, cid), user)
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
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """Accept the upload, enqueue processing, return 202. Poll .../status (A6)."""
    import storage
    from tasks import process_claim

    cid = claim_id.strip()
    existing = db.get(Claim, cid)
    if existing and existing.hospital_id != user.hospital_id:
        raise HTTPException(403, "claim id belongs to another hospital")
    log.info("create_claim: %s (%d file(s), hospital=%s)",
             cid, len(files), user.hospital_id)

    # 1) Upload document bytes to object storage; record metadata.
    docs = []
    for uf in files:
        blob = await uf.read()
        key = storage.document_key(cid, uf.filename)
        storage.put_bytes(key, blob, uf.content_type)
        docs.append(Document(filename=uf.filename, content_type=uf.content_type,
                             storage_key=key, size_bytes=len(blob)))

    # 2) Create/replace the claim row as QUEUED.
    claim = existing or Claim(id=cid)
    claim.hospital_id = user.hospital_id
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

    # 3) Hand off to the worker and return right away.
    async_result = process_claim.delay(cid)
    claim.task_id = async_result.id
    claim.stage = "queued"
    db.commit()
    log.info("[%s] QUEUED — task %s", cid, async_result.id)
    jobs.info("task=%s claim=%s hospital=%s stage=queued",
              async_result.id, cid, user.hospital_id)
    return {"id": cid, "status": "QUEUED", "task_id": async_result.id}


@app.get("/api/claims/{cid}/status")
def claim_status(cid: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Lightweight polling endpoint — status + live stage, no heavy payload."""
    claim = _owned_or_404(db.get(Claim, cid), user)
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


@app.put("/api/claims/{cid}")
def update_claim(cid: str, ext: dict, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    from validator import validate

    claim = _owned_or_404(db.get(Claim, cid), user)
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
def approve(cid: str, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    from fhir_builder import build_bundle

    claim = _owned_or_404(db.get(Claim, cid), user)
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
def download_bundle(cid: str, token: str = "", db: Session = Depends(get_db)):
    user = user_from_query_token(token, db)
    claim = _owned_or_404(db.get(Claim, cid), user)
    if not claim.bundle:
        raise HTTPException(404, "no bundle — approve the claim first")
    log.info("bundle download: %s", cid)
    return Response(json.dumps(claim.bundle, indent=2),
                    media_type="application/fhir+json",
                    headers={"Content-Disposition":
                             f'attachment; filename="{cid}_bundle.json"'})


@app.get("/api/claims/{cid}/documents/{name}/preview")
def doc_preview(cid: str, name: str, page: int = 0, token: str = "",
                db: Session = Depends(get_db)):
    """PNG render of a page (poppler), or {'text': ...} fallback. Auth via ?token
    (an <img>/<a> can't send an Authorization header). Bytes come from storage."""
    import storage

    user = user_from_query_token(token, db)
    claim = _owned_or_404(db.get(Claim, cid), user)
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


# --- task tracking ---------------------------------------------------------
@app.get("/api/tasks")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """All processing jobs for this hospital, newest first."""
    claims = db.execute(
        select(Claim).where(Claim.task_id.isnot(None),
                            Claim.hospital_id == user.hospital_id)
        .order_by(Claim.updated_at.desc())).scalars().all()
    log.info("list_tasks(%s) -> %d job(s)", user.hospital_id, len(claims))
    return [c.job() for c in claims]


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Track one job by its Celery task id (scoped to the caller's hospital)."""
    claim = db.execute(
        select(Claim).where(Claim.task_id == task_id)).scalar_one_or_none()
    claim = _owned_or_404(claim, user)
    view = claim.job()
    try:                                   # best-effort — backend may have expired
        from tasks import celery_app
        view["celery_state"] = celery_app.AsyncResult(task_id).state
    except Exception:
        view["celery_state"] = None
    log.info("get_task: %s stage=%s status=%s", task_id, claim.stage, claim.status)
    return view
