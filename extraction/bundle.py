#!/usr/bin/env python3
"""Phase 3 runner: extracted claims -> validation report + FHIR bundle.

  python bundle.py --claims claims_out --out fhir_out

For each claims_out/Pxxx.json produces:
  fhir_out/Pxxx_validation.json   rule-engine report (PASS/REVIEW/FAIL)
  fhir_out/Pxxx_bundle.json       FHIR R4 bundle (built even on REVIEW;
                                  skipped on FAIL — unsubmittable anyway)
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fhir_builder import build_bundle
from validator import validate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--out", default="fhir_out")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    results = []
    for path in sorted(glob.glob(os.path.join(a.claims, "P*.json"))):
        pid = os.path.splitext(os.path.basename(path))[0]
        with open(path) as f:
            ext = json.load(f)

        report = validate(ext)
        with open(os.path.join(a.out, f"{pid}_validation.json"), "w") as f:
            json.dump(report, f, indent=2)

        bundle_path = None
        if report["status"] != "FAIL":
            bundle = build_bundle(ext)
            bundle_path = os.path.join(a.out, f"{pid}_bundle.json")
            with open(bundle_path, "w") as f:
                f.write(bundle.model_dump_json(indent=2))

        s = report["summary"]
        flag_txt = "" if report["status"] == "PASS" else \
            " | " + "; ".join(c["check"] for c in report["checks"]
                              if c["result"] != "PASS")[:90]
        print(f"[{pid}] {report['status']:6s} "
              f"({s['passed']}/{s['total_checks']} checks"
              f", {s['review_flags']} review, {s['failures']} fail)"
              f"{' -> ' + os.path.basename(bundle_path) if bundle_path else ''}"
              f"{flag_txt}")
        results.append((pid, report["status"]))

    n = len(results)
    print(f"\n{n} claims: "
          f"{sum(1 for _, s in results if s=='PASS')} PASS, "
          f"{sum(1 for _, s in results if s=='REVIEW')} REVIEW, "
          f"{sum(1 for _, s in results if s=='FAIL')} FAIL -> {a.out}/")


if __name__ == "__main__":
    main()
