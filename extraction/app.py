#!/usr/bin/env python3
"""ClaimBridge — review console (Phase 4).

Run:  streamlit run app.py
Needs the same env as the pipeline (LLM_PROVIDER + key). Data lives in
./app_data (claims, validations, bundles) so state survives restarts.

Flow: Upload PDFs -> Process (extract + code) -> Review (fields, flags,
edits) -> Approve -> FHIR bundle -> Dashboard.
"""

import base64
import io
import json
import os
import sys
import time
from datetime import datetime

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "app_data")
for sub in ("uploads", "claims", "validations", "bundles"):
    os.makedirs(os.path.join(DATA, sub), exist_ok=True)

# ---------------------------------------------------------------- helpers

TEAL, AMBER, RED, INK = "#0E7C66", "#C67B1F", "#B3402F", "#14273D"

st.set_page_config(page_title="ClaimBridge", page_icon="🩺", layout="wide")
st.markdown(f"""<style>
  .stApp h1, .stApp h2, .stApp h3 {{ color:{INK}; }}
  div[data-testid="stMetricValue"] {{ color:{INK}; }}
  .pill {{ display:inline-block; padding:2px 12px; border-radius:999px;
          font-size:0.8rem; font-weight:600; }}
  .p-pass {{ background:#E3F1EC; color:{TEAL}; }}
  .p-review {{ background:#FBF1DF; color:{AMBER}; }}
  .p-fail {{ background:#F9E9E5; color:{RED}; }}
  .conf-hi {{ color:{TEAL}; font-weight:600; font-size:0.8rem; }}
  .conf-lo {{ color:{AMBER}; font-weight:600; font-size:0.8rem; }}
</style>""", unsafe_allow_html=True)


def pill(status):
    cls = {"PASS": "p-pass", "REVIEW": "p-review", "FAIL": "p-fail",
           "APPROVED": "p-pass", "DRAFT": "p-review"}.get(status, "p-review")
    return f'<span class="pill {cls}">{status}</span>'


def list_claims():
    out = []
    for f in sorted(os.listdir(os.path.join(DATA, "claims"))):
        if not f.endswith(".json"):
            continue
        cid = f[:-5]
        with open(os.path.join(DATA, "claims", f)) as fh:
            ext = json.load(fh)
        vpath = os.path.join(DATA, "validations", f"{cid}.json")
        report = json.load(open(vpath)) if os.path.exists(vpath) else None
        bundled = os.path.exists(os.path.join(DATA, "bundles", f"{cid}.json"))
        out.append((cid, ext, report, bundled))
    return out


def save_claim(cid, ext_dict):
    with open(os.path.join(DATA, "claims", f"{cid}.json"), "w") as f:
        json.dump(ext_dict, f, indent=2)


def revalidate(cid, ext_dict):
    from validator import validate
    report = validate(ext_dict)
    with open(os.path.join(DATA, "validations", f"{cid}.json"), "w") as f:
        json.dump(report, f, indent=2)
    return report


def process_documents(cid, files):
    """files: list of (name, bytes). Runs the Phase 2 pipeline on them."""
    from coder import assign_codes, default_indexes
    from extractor import extract_claim
    from llm import get_llm
    from pypdf import PdfReader

    updir = os.path.join(DATA, "uploads", cid)
    os.makedirs(updir, exist_ok=True)
    texts, images = [], []
    for name, blob in files:
        path = os.path.join(updir, name)
        with open(path, "wb") as f:
            f.write(blob)
        if name.lower().endswith((".png", ".jpg", ".jpeg")):
            images.append(base64.b64encode(blob).decode())
            continue
        reader = PdfReader(io.BytesIO(blob))
        text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        if len(text) > 100:
            texts.append(f"[{name}]\n{text}")
        else:
            from pdf2image import convert_from_bytes
            for img in convert_from_bytes(blob, dpi=150)[:5]:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                images.append(base64.b64encode(buf.getvalue()).decode())

    llm = get_llm()
    claim = extract_claim(llm, cid, texts, images)
    claim.source_documents = [n for n, _ in files]
    icd, snomed = default_indexes()
    assign_codes(claim, llm, icd, snomed)
    ext = json.loads(claim.model_dump_json())
    save_claim(cid, ext)
    revalidate(cid, ext)
    return ext


def doc_preview(cid):
    updir = os.path.join(DATA, "uploads", cid)
    if not os.path.isdir(updir):
        st.info("No source documents stored for this claim.")
        return
    files = sorted(os.listdir(updir))
    pick = st.selectbox("Source document", files, key=f"doc_{cid}")
    path = os.path.join(updir, pick)
    if pick.lower().endswith((".png", ".jpg", ".jpeg")):
        st.image(path, use_container_width=True)
        return
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(path, dpi=110)
        for pg in pages[:3]:
            st.image(pg, use_container_width=True)
    except Exception:
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
        st.text_area("Document text", text, height=420, key=f"txt_{cid}")


def conf_badge(conf):
    if conf is None:
        return ""
    cls = "conf-hi" if conf >= 0.85 else "conf-lo"
    tag = f"{conf*100:.0f}%" + ("" if conf >= 0.85 else " — confirm")
    return f'<span class="{cls}">{tag}</span>'


# ---------------------------------------------------------------- layout

st.title("🩺 ClaimBridge")
st.caption("Messy hospital documents → validated, NHCX-ready claims")

tab_dash, tab_upload, tab_review = st.tabs(
    ["📋 Claims", "⬆️ Upload & process", "🔍 Review"])

# ------------------------------------------------------------- dashboard
with tab_dash:
    claims = list_claims()
    if not claims:
        st.info("No claims yet — start in the Upload tab.")
    else:
        n_pass = sum(1 for _, _, r, _ in claims if r and r["status"] == "PASS")
        n_rev = sum(1 for _, _, r, _ in claims if r and r["status"] == "REVIEW")
        n_bund = sum(1 for *_, b in claims if b)
        total_amt = sum((c.get("billing") or {}).get("grand_total") or 0
                        for _, c, _, _ in claims)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Claims", len(claims))
        m2.metric("Clean / need review", f"{n_pass} / {n_rev}")
        m3.metric("FHIR bundles built", n_bund)
        m4.metric("Total claim value", f"₹{total_amt:,.0f}")
        st.divider()
        for cid, ext, report, bundled in claims:
            p = ext.get("patient") or {}
            b = ext.get("billing") or {}
            c1, c2, c3, c4, c5 = st.columns([2, 3, 2, 2, 2])
            c1.markdown(f"**{cid}**")
            c2.markdown(f"{p.get('name','?')} · {p.get('uhid','')}")
            c3.markdown(f"₹{(b.get('grand_total') or 0):,.0f}")
            status = "APPROVED" if bundled else (report["status"] if report else "DRAFT")
            c4.markdown(pill(status), unsafe_allow_html=True)
            if bundled:
                with open(os.path.join(DATA, "bundles", f"{cid}.json"), "rb") as f:
                    c5.download_button("FHIR bundle", f, file_name=f"{cid}_bundle.json",
                                       key=f"dl_{cid}")

# ---------------------------------------------------------------- upload
with tab_upload:
    st.subheader("Upload a patient's documents")
    st.caption("Discharge summary, final bill, lab reports — PDFs, scans, or photos.")
    cid = st.text_input("Claim reference (e.g. patient UHID or any ID)",
                        value=f"CLM-{datetime.now():%y%m%d-%H%M}")
    uploads = st.file_uploader("Drop files here", type=["pdf", "png", "jpg", "jpeg"],
                               accept_multiple_files=True)
    if st.button("Process documents", type="primary",
                 disabled=not (cid and uploads)):
        with st.status("Running the claims engine…", expanded=True) as s:
            st.write(f"Reading {len(uploads)} document(s)…")
            t0 = time.time()
            try:
                ext = process_documents(cid.strip(), [(u.name, u.getvalue())
                                                      for u in uploads])
                st.write(f"Extraction + coding done in {time.time()-t0:.1f}s")
                report = json.load(open(os.path.join(DATA, "validations",
                                                     f"{cid.strip()}.json")))
                s.update(label=f"Done — validation: {report['status']}",
                         state="complete")
                st.success("Open the Review tab to check and approve this claim.")
            except Exception as e:
                s.update(label="Failed", state="error")
                st.error(f"{type(e).__name__}: {e}")

# ---------------------------------------------------------------- review
with tab_review:
    claims = list_claims()
    if not claims:
        st.info("Nothing to review yet.")
    else:
        ids = [cid for cid, *_ in claims]
        sel = st.selectbox("Claim", ids)
        cid, ext, report, bundled = next(c for c in claims if c[0] == sel)

        left, right = st.columns([1, 1], gap="large")
        with left:
            st.subheader("Source documents")
            doc_preview(cid)

        with right:
            p = ext.get("patient") or {}
            e = ext.get("encounter") or {}
            cov = ext.get("coverage") or {}
            b = ext.get("billing") or {}

            st.subheader("Extracted claim")
            c1, c2 = st.columns(2)
            p["name"] = c1.text_input("Patient name", p.get("name") or "", key="f_name")
            p["uhid"] = c2.text_input("UHID", p.get("uhid") or "", key="f_uhid")
            c3, c4 = st.columns(2)
            e["admission_datetime"] = c3.text_input(
                "Admission", e.get("admission_datetime") or "", key="f_adm")
            e["discharge_datetime"] = c4.text_input(
                "Discharge", e.get("discharge_datetime") or "", key="f_dis")
            c5, c6 = st.columns(2)
            cov["insurer"] = c5.text_input("Insurer", cov.get("insurer") or "", key="f_ins")
            cov["policy_number"] = c6.text_input(
                "Policy no.", cov.get("policy_number") or "", key="f_pol")

            st.markdown("**Diagnoses**")
            for i, dx in enumerate(ext.get("diagnoses") or []):
                d1, d2 = st.columns([3, 2])
                d1.markdown(f"{dx.get('text','')}")
                code = d2.text_input("ICD-10", dx.get("icd10_code") or "",
                                     key=f"f_icd_{i}", label_visibility="collapsed")
                dx["icd10_code"] = code or None
                d2.markdown(conf_badge(dx.get("coding_confidence")),
                            unsafe_allow_html=True)

            for i, pr in enumerate(ext.get("procedures") or []):
                st.markdown(f"**Procedure:** {pr.get('text','')} · "
                            f"SNOMED `{pr.get('snomed_code','—')}` ",
                            unsafe_allow_html=True)
                st.markdown(conf_badge(pr.get("coding_confidence")),
                            unsafe_allow_html=True)

            st.markdown(f"**Bill:** {len(b.get('line_items') or [])} items · "
                        f"grand total **₹{(b.get('grand_total') or 0):,.0f}**")

            # validation report
            if report:
                st.markdown(f"**Validation:** {pill(report['status'])}",
                            unsafe_allow_html=True)
                flagged = [c for c in report["checks"] if c["result"] != "PASS"]
                for c in flagged:
                    icon = "🟠" if c["result"] == "REVIEW" else "🔴"
                    st.markdown(f"{icon} **{c['code']}** {c['check']} — {c['detail']}")
                with st.expander(f"All {len(report['checks'])} checks"):
                    for c in report["checks"]:
                        mark = {"PASS": "✅", "REVIEW": "🟠", "FAIL": "🔴"}[c["result"]]
                        st.markdown(f"{mark} {c['code']} {c['check']}")

            a1, a2 = st.columns(2)
            if a1.button("Save edits & re-validate", key="btn_save"):
                save_claim(cid, ext)
                report = revalidate(cid, ext)
                st.rerun()
            can_approve = report and report["status"] != "FAIL"
            if a2.button("✅ Approve → build FHIR bundle", type="primary",
                         disabled=not can_approve, key="btn_approve"):
                from fhir_builder import build_bundle
                bundle = build_bundle(ext)
                with open(os.path.join(DATA, "bundles", f"{cid}.json"), "w") as f:
                    f.write(bundle.model_dump_json(indent=2))
                st.success("FHIR bundle built — download it from the Claims tab. "
                           "(Phase 5 wires this to NHCX sandbox submission.)")
                st.balloons()
