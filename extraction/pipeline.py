#!/usr/bin/env python3
"""Phase 2 pipeline: patient documents -> extracted, coded claim JSON.

Usage:
  python pipeline.py --docs-dir <corpus/documents> [--scans-dir <...>]
                     [--patients P001,P002] [--out claims_out]

Data access goes through the same logic as the MCP server tools (text layer
if present, page images if scanned) so this pipeline behaves identically
whether fed by MCP in production or by folders in development.
"""

import argparse
import base64
import glob
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coder import assign_codes, default_indexes
from extractor import extract_claim
from llm import get_llm


def read_pdf(path):
    """-> (text or None, [images_b64] or None)  — same dual-mode as the MCP tool."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    if len(text) > 100:
        return text, None
    from pdf2image import convert_from_path
    pages = convert_from_path(path, dpi=150)
    images = []
    for img in pages[:5]:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        images.append(base64.b64encode(buf.getvalue()).decode())
    return None, images


def patient_ids(docs_dir):
    ids = set()
    for p in glob.glob(os.path.join(docs_dir, "*.pdf")):
        m = re.match(r"(P\d+)_", os.path.basename(p))
        if m:
            ids.add(m.group(1))
    return sorted(ids)


def run(docs_dir, scans_dir, only, out_dir, prefer_scans=False):
    os.makedirs(out_dir, exist_ok=True)
    llm = get_llm()
    icd, snomed = default_indexes()
    pids = only or patient_ids(docs_dir)

    results = {}
    for pid in pids:
        t0 = time.time()
        files = sorted(glob.glob(os.path.join(docs_dir, f"{pid}_*.pdf")))
        if prefer_scans and scans_dir:
            for i, f in enumerate(files):
                scanned = os.path.join(scans_dir,
                                       os.path.basename(f).replace(".pdf", "_scanned.pdf"))
                if os.path.exists(scanned):
                    files[i] = scanned
        if not files:
            print(f"[{pid}] no documents found, skipping")
            continue

        texts, images = [], []
        for f in files:
            t, imgs = read_pdf(f)
            if t:
                texts.append(f"[{os.path.basename(f)}]\n{t}")
            if imgs:
                images.extend(imgs)

        try:
            claim = extract_claim(llm, pid, texts, images)
            claim.source_documents = [os.path.basename(f) for f in files]
            assign_codes(claim, llm, icd, snomed)
            out_path = os.path.join(out_dir, f"{pid}.json")
            with open(out_path, "w") as f:
                f.write(claim.model_dump_json(indent=2))
            dt = time.time() - t0
            ndx = len(claim.diagnoses)
            coded = sum(1 for d in claim.diagnoses if d.icd10_code)
            print(f"[{pid}] extracted in {dt:.1f}s -> {out_path} "
                  f"(diagnoses: {ndx}, coded: {coded}, "
                  f"total: {claim.billing.grand_total})")
            results[pid] = out_path
        except Exception as e:
            print(f"[{pid}] FAILED: {e}")

    print(f"\nDone: {len(results)}/{len(pids)} patients -> {out_dir}/")
    print("Next: python evaluate.py --claims", out_dir,
          "--ground-truth <path to ground_truth.json>")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs-dir", required=True)
    ap.add_argument("--scans-dir", default=None)
    ap.add_argument("--patients", default=None, help="comma-separated, e.g. P001,P003")
    ap.add_argument("--out", default="claims_out")
    ap.add_argument("--prefer-scans", action="store_true",
                    help="use scanned variants where available (vision stress test)")
    a = ap.parse_args()
    run(a.docs_dir, a.scans_dir,
        a.patients.split(",") if a.patients else None, a.out, a.prefer_scans)
