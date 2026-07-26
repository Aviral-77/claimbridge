"""Celery task queue — async claim processing (Phase A4).

`process_claim` runs the extract -> code -> validate pipeline off the API
process, on a worker. The worker fetches document bytes from S3 (A3), runs the
(unchanged) engine, and writes the result back to the DB.

Worker:  celery -A tasks.celery_app worker --loglevel=info -c 4
"""

import base64
import io
import json
import os
import sys
import time

from celery import Celery

# Ensure this directory is importable so the worker can load local modules
# (storage, db, models, and the engine) — the Celery console script does not put
# the working dir on sys.path the way `uvicorn api:app` does.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from logging_setup import get_logger  # noqa: E402

log = get_logger("tasks")
jobs = get_logger("jobs")     # dedicated job-lifecycle log (logs/jobs.log)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery("claimbridge", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_track_started=True,      # exposes a STARTED state while running
    result_expires=3600,          # drop results after an hour
)


def _derive(ext: dict, report: dict | None):
    patient = (ext.get("patient") or {}).get("name")
    uhid = (ext.get("patient") or {}).get("uhid")
    amount = (ext.get("billing") or {}).get("grand_total")
    flags = (report or {}).get("summary", {}).get("review_flags", 0)
    return patient, uhid, amount, flags


@celery_app.task(bind=True, name="process_claim")
def process_claim(self, cid: str) -> dict:
    """RUNNING -> extract -> code -> validate -> persist. Records the task id and
    a live `stage` on the claim, and logs the lifecycle to jobs.log. Sets status
    to the validator result (PASS/REVIEW/FAIL), or FAIL + error on exception."""
    import storage
    from db import SessionLocal
    from models import Claim

    task_id = self.request.id
    db = SessionLocal()

    def set_stage(s: str) -> None:
        claim.stage = s
        db.commit()
        jobs.info("task=%s claim=%s stage=%s", task_id, cid, s)

    try:
        claim = db.get(Claim, cid)
        if not claim:
            log.error("process_claim: %s not found", cid)
            jobs.error("task=%s claim=%s not found", task_id, cid)
            return {"id": cid, "status": "FAIL", "error": "claim not found"}

        claim.task_id = task_id
        claim.status = "RUNNING"
        set_stage("reading")
        log.info("[%s] RUNNING (task %s, %d document(s))",
                 cid, task_id, len(claim.documents))
        t0 = time.time()

        # --- read documents back from object storage ---
        from pypdf import PdfReader
        texts, images = [], []
        for doc in claim.documents:
            blob = storage.get_bytes(doc.storage_key)
            name = doc.filename.lower()
            if name.endswith((".png", ".jpg", ".jpeg")):
                images.append(base64.b64encode(blob).decode())
                continue
            reader = PdfReader(io.BytesIO(blob))
            text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
            if len(text) > 100:
                texts.append(f"[{doc.filename}]\n{text}")
            else:
                log.info("[%s] %s has no text layer — rendering", cid, doc.filename)
                from pdf2image import convert_from_bytes
                for img in convert_from_bytes(blob, dpi=150)[:5]:
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    images.append(base64.b64encode(buf.getvalue()).decode())
        log.info("[%s] %d text doc(s), %d image(s)", cid, len(texts), len(images))

        # --- the engine (unchanged) ---
        from coder import assign_codes, default_indexes
        from extractor import extract_claim
        from llm import get_llm
        from validator import validate

        llm = get_llm()
        set_stage("extracting")
        log.info("[%s] extracting fields", cid)
        claim_obj = extract_claim(llm, cid, texts, images)
        claim_obj.source_documents = [d.filename for d in claim.documents]
        set_stage("coding")
        log.info("[%s] assigning ICD-10 / SNOMED codes", cid)
        icd, snomed = default_indexes()
        assign_codes(claim_obj, llm, icd, snomed)
        ext = json.loads(claim_obj.model_dump_json())
        set_stage("validating")
        log.info("[%s] running validation", cid)
        report = validate(ext)
        patient, uhid, amount, flags = _derive(ext, report)

        claim.extraction = ext
        claim.validation = report
        claim.status = report["status"]
        claim.approved = False
        claim.bundle = None
        claim.patient_name, claim.uhid, claim.amount, claim.flags = patient, uhid, amount, flags
        claim.seconds = round(time.time() - t0, 1)
        claim.error = None
        claim.stage = "done"
        db.commit()
        jobs.info("task=%s claim=%s stage=done status=%s seconds=%.1f",
                  task_id, cid, report["status"], claim.seconds)
        log.info("[%s] done: %s in %.1fs (flags=%s)",
                 cid, report["status"], claim.seconds, flags)
        return {"id": cid, "status": report["status"], "seconds": claim.seconds}

    except Exception as e:
        log.exception("[%s] processing failed", cid)
        jobs.exception("task=%s claim=%s stage=failed error=%s", task_id, cid, e)
        try:
            claim = db.get(Claim, cid)
            if claim:
                claim.status = "FAIL"
                claim.stage = "failed"
                claim.error = str(e)[:2000]
                db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
