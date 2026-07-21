#!/usr/bin/env python3
"""ClaimBridge API — FastAPI backend for the React frontend.

Run (from the extraction/ folder):
  pip install fastapi uvicorn python-multipart
  uvicorn api:app --reload --port 8000

Wraps the existing engine (extractor/coder/validator/fhir_builder). State
lives in ./app_data exactly like the Streamlit app, so both UIs coexist.
"""

import base64
import io
import json
import os
import sys
import time
from typing import List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "app_data")
for sub in ("uploads", "claims", "validations", "bundles"):
    os.makedirs(os.path.join(DATA, sub), exist_ok=True)

app = FastAPI(title="ClaimBridge API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

# --- demo auth -------------------------------------------------------------
# Demo-grade: fixed users, opaque token. Production replaces this with real
# identity (JWT, hashed passwords, roles) — tracked as a Phase 6 task.
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
        raise HTTPException(401, "Email or password is incorrect")
    token = base64.urlsafe_b64encode(os.urandom(24)).decode()
    _TOKENS[token] = email
    return {"token": token, "name": user["name"], "org": user["org"],
            "email": email}


@app.post("/api/logout")
def logout(body: dict):
    _TOKENS.pop(body.get("token"), None)
    return {"ok": True}


def _paths(cid):
    return {
        "claim": os.path.join(DATA, "claims", f"{cid}.json"),
        "validation": os.path.join(DATA, "validations", f"{cid}.json"),
        "bundle": os.path.join(DATA, "bundles", f"{cid}.json"),
        "uploads": os.path.join(DATA, "uploads", cid),
    }


def _load(path):
    return json.load(open(path)) if os.path.exists(path) else None


def _summary(cid):
    p = _paths(cid)
    ext = _load(p["claim"])
    if not ext:
        return None
    report = _load(p["validation"])
    return {
        "id": cid,
        "patient": (ext.get("patient") or {}).get("name"),
        "uhid": (ext.get("patient") or {}).get("uhid"),
        "amount": (ext.get("billing") or {}).get("grand_total"),
        "status": "APPROVED" if os.path.exists(p["bundle"])
                  else (report or {}).get("status", "DRAFT"),
        "flags": (report or {}).get("summary", {}).get("review_flags", 0),
    }


@app.get("/api/claims")
def list_claims():
    ids = sorted(f[:-5] for f in os.listdir(os.path.join(DATA, "claims"))
                 if f.endswith(".json"))
    return [s for s in (_summary(c) for c in ids) if s]


@app.get("/api/claims/{cid}")
def get_claim(cid: str):
    p = _paths(cid)
    ext = _load(p["claim"])
    if not ext:
        raise HTTPException(404, "claim not found")
    docs = sorted(os.listdir(p["uploads"])) if os.path.isdir(p["uploads"]) else []
    return {"id": cid, "extraction": ext, "validation": _load(p["validation"]),
            "documents": docs, "approved": os.path.exists(p["bundle"])}


@app.post("/api/claims")
async def create_claim(claim_id: str = Form(...),
                       files: List[UploadFile] = File(...)):
    from coder import assign_codes, default_indexes
    from extractor import extract_claim
    from llm import get_llm
    from pypdf import PdfReader

    cid = claim_id.strip()
    p = _paths(cid)
    os.makedirs(p["uploads"], exist_ok=True)

    texts, images = [], []
    t0 = time.time()
    for uf in files:
        blob = await uf.read()
        with open(os.path.join(p["uploads"], uf.filename), "wb") as f:
            f.write(blob)
        name = uf.filename.lower()
        if name.endswith((".png", ".jpg", ".jpeg")):
            images.append(base64.b64encode(blob).decode())
            continue
        reader = PdfReader(io.BytesIO(blob))
        text = "\n".join((pg.extract_text() or "") for pg in reader.pages).strip()
        if len(text) > 100:
            texts.append(f"[{uf.filename}]\n{text}")
        else:
            from pdf2image import convert_from_bytes
            for img in convert_from_bytes(blob, dpi=150)[:5]:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                images.append(base64.b64encode(buf.getvalue()).decode())

    try:
        llm = get_llm()
        claim = extract_claim(llm, cid, texts, images)
        claim.source_documents = [uf.filename for uf in files]
        icd, snomed = default_indexes()
        assign_codes(claim, llm, icd, snomed)
    except Exception as e:
        raise HTTPException(500, f"extraction failed: {e}")

    ext = json.loads(claim.model_dump_json())
    with open(p["claim"], "w") as f:
        json.dump(ext, f, indent=2)
    from validator import validate
    report = validate(ext)
    with open(p["validation"], "w") as f:
        json.dump(report, f, indent=2)
    return {"id": cid, "seconds": round(time.time() - t0, 1),
            "status": report["status"]}


@app.put("/api/claims/{cid}")
def update_claim(cid: str, ext: dict):
    p = _paths(cid)
    if not os.path.exists(p["claim"]):
        raise HTTPException(404, "claim not found")
    with open(p["claim"], "w") as f:
        json.dump(ext, f, indent=2)
    from validator import validate
    report = validate(ext)
    with open(p["validation"], "w") as f:
        json.dump(report, f, indent=2)
    return {"id": cid, "status": report["status"], "validation": report}


@app.post("/api/claims/{cid}/approve")
def approve(cid: str):
    p = _paths(cid)
    ext = _load(p["claim"])
    report = _load(p["validation"])
    if not ext:
        raise HTTPException(404, "claim not found")
    if not report or report["status"] == "FAIL":
        raise HTTPException(409, "claim has failing checks — fix before approving")
    from fhir_builder import build_bundle
    bundle = build_bundle(ext)
    with open(p["bundle"], "w") as f:
        f.write(bundle.model_dump_json(indent=2))
    return {"id": cid, "approved": True}


@app.get("/api/claims/{cid}/bundle")
def download_bundle(cid: str):
    p = _paths(cid)
    if not os.path.exists(p["bundle"]):
        raise HTTPException(404, "no bundle — approve the claim first")
    return Response(open(p["bundle"], "rb").read(),
                    media_type="application/fhir+json",
                    headers={"Content-Disposition":
                             f'attachment; filename="{cid}_bundle.json"'})


@app.get("/api/claims/{cid}/documents/{name}/preview")
def doc_preview(cid: str, name: str, page: int = 0):
    """PNG render of a page (poppler), or {'text': ...} fallback."""
    p = _paths(cid)
    path = os.path.realpath(os.path.join(p["uploads"], name))
    if not path.startswith(os.path.realpath(p["uploads"])) or not os.path.exists(path):
        raise HTTPException(404, "document not found")
    if path.lower().endswith((".png", ".jpg", ".jpeg")):
        return Response(open(path, "rb").read(), media_type="image/png")
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(path, dpi=110,
                                  first_page=page + 1, last_page=page + 1)
        buf = io.BytesIO()
        pages[0].save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png")
    except Exception:
        from pypdf import PdfReader
        text = "\n".join((pg.extract_text() or "")
                         for pg in PdfReader(path).pages)
        return JSONResponse({"text": text})
