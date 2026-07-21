#!/usr/bin/env python3
"""Grade extracted claims against ground_truth.json — the accuracy exam.

  python evaluate.py --claims claims_out --ground-truth .../ground_truth.json

Scoring:
  exact fields  : uhid, ip_number, dates, policy_number, icd10 codes, totals
  fuzzy fields  : names, address, insurer (>=90 token_set_ratio counts)
  lists         : medications/labs/bill items scored by count coverage
Outputs overall + per-patient + per-field-group accuracy.
"""

import argparse
import json
import os
import sys

from rapidfuzz import fuzz
from rich.console import Console
from rich.table import Table

C = Console()


def norm(x):
    if x is None:
        return None
    s = str(x).strip().lower()
    return s.replace(",", "").replace("  ", " ") or None


def eq_exact(a, b):
    return norm(a) == norm(b)


def eq_num(a, b, tol=1.0):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def eq_fuzzy(a, b, threshold=90):
    if not a or not b:
        return a == b
    return fuzz.token_set_ratio(str(a).lower(), str(b).lower()) >= threshold


def eq_datetime(a, b):
    if not a or not b:
        return a == b
    na, nb = norm(a)[:16], norm(b)[:16]      # compare to minute precision
    return na.replace("t", " ") == nb.replace("t", " ")


def grade_patient(got, exp):
    """Returns list of (field, ok:bool, got, expected)."""
    checks = []
    g_p, e_p = got.get("patient", {}), exp["patient"]
    checks += [
        ("patient.name", eq_fuzzy(g_p.get("name"), e_p["name"]), g_p.get("name"), e_p["name"]),
        ("patient.age", eq_num(g_p.get("age"), e_p["age"], 0), g_p.get("age"), e_p["age"]),
        ("patient.gender", eq_exact(g_p.get("gender"), e_p["gender"]), g_p.get("gender"), e_p["gender"]),
        ("patient.uhid", eq_exact(g_p.get("uhid"), e_p["uhid"]), g_p.get("uhid"), e_p["uhid"]),
        ("patient.phone", eq_exact(g_p.get("phone"), e_p["phone"]), g_p.get("phone"), e_p["phone"]),
    ]
    g_e, e_e = got.get("encounter", {}), exp["encounter"]
    checks += [
        ("encounter.ip_number", eq_exact(g_e.get("ip_number"), e_e["ip_number"]),
         g_e.get("ip_number"), e_e["ip_number"]),
        ("encounter.admission", eq_datetime(g_e.get("admission_datetime"), e_e["admission_datetime"]),
         g_e.get("admission_datetime"), e_e["admission_datetime"]),
        ("encounter.discharge", eq_datetime(g_e.get("discharge_datetime"), e_e["discharge_datetime"]),
         g_e.get("discharge_datetime"), e_e["discharge_datetime"]),
        ("encounter.consultant", eq_fuzzy(g_e.get("consultant"), e_e["consultant"]),
         g_e.get("consultant"), e_e["consultant"]),
    ]
    # diagnoses: text captured + ICD correct
    g_dx = got.get("diagnoses", [])
    for i, e_dx in enumerate(exp["diagnoses"]):
        gd = g_dx[i] if i < len(g_dx) else {}
        checks.append((f"diagnosis[{i}].text",
                       eq_fuzzy(gd.get("text"), e_dx["text"], 80),
                       gd.get("text"), e_dx["text"]))
        checks.append((f"diagnosis[{i}].icd10",
                       eq_exact(gd.get("icd10_code"), e_dx["icd10_code"]),
                       gd.get("icd10_code"), e_dx["icd10_code"]))
    # procedures
    g_pr = got.get("procedures", [])
    for i, e_pr in enumerate(exp["procedures"]):
        gp = g_pr[i] if i < len(g_pr) else {}
        checks.append((f"procedure[{i}].text",
                       eq_fuzzy(gp.get("text"), e_pr["text"], 80),
                       gp.get("text"), e_pr["text"]))
        if e_pr.get("snomed_code"):
            checks.append((f"procedure[{i}].snomed",
                           eq_exact(gp.get("snomed_code"), e_pr["snomed_code"]),
                           gp.get("snomed_code"), e_pr["snomed_code"]))
    # spurious extras are errors too (a claim with an invented procedure is
    # worse than a missing one)
    checks.append(("diagnoses.no_extras", len(g_dx) <= len(exp["diagnoses"]),
                   len(g_dx), len(exp["diagnoses"])))
    checks.append(("procedures.no_extras", len(g_pr) <= len(exp["procedures"]),
                   len(g_pr), len(exp["procedures"])))
    # billing
    g_b, e_b = got.get("billing", {}), exp["billing"]
    checks += [
        ("billing.n_items", len(g_b.get("line_items", [])) == len(e_b["line_items"]),
         len(g_b.get("line_items", [])), len(e_b["line_items"])),
        ("billing.sub_total", eq_num(g_b.get("sub_total"), e_b["sub_total"]),
         g_b.get("sub_total"), e_b["sub_total"]),
        ("billing.grand_total", eq_num(g_b.get("grand_total"), e_b["grand_total"]),
         g_b.get("grand_total"), e_b["grand_total"]),
    ]
    # coverage
    g_c, e_c = got.get("coverage", {}), exp["coverage"]
    checks += [
        ("coverage.insurer", eq_fuzzy(g_c.get("insurer"), e_c["insurer"]),
         g_c.get("insurer"), e_c["insurer"]),
        ("coverage.policy_number", eq_exact(g_c.get("policy_number"), e_c["policy_number"]),
         g_c.get("policy_number"), e_c["policy_number"]),
        ("coverage.mode", eq_exact(g_c.get("mode"), e_c["mode"]),
         g_c.get("mode"), e_c["mode"]),
    ]
    # meds & labs coverage counts
    checks.append(("medications.count",
                   len(got.get("medications_on_discharge", [])) == len(exp["medications_on_discharge"]),
                   len(got.get("medications_on_discharge", [])), len(exp["medications_on_discharge"])))
    checks.append(("labs.count", len(got.get("labs", [])) == len(exp["labs"]),
                   len(got.get("labs", [])), len(exp["labs"])))
    return checks


def group_of(field):
    if field.startswith("diagnosis") and "icd10" in field:
        return "CODING (ICD-10)"
    if field.startswith("procedure") and "snomed" in field:
        return "CODING (SNOMED)"
    if field.startswith("billing"):
        return "BILLING"
    if field.startswith(("patient", "encounter", "coverage")):
        return "DEMOGRAPHICS/ENCOUNTER/COVERAGE"
    return "CLINICAL CONTENT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--ground-truth", required=True)
    a = ap.parse_args()

    with open(a.ground_truth) as f:
        gt_raw = json.load(f)
    gts = {}
    for g in gt_raw:
        exp = g["expected_extraction"]
        # corporate discharge layout never prints a phone number — expecting
        # one there was a ground-truth bug; null is the CORRECT extraction.
        layout = (g.get("documents", {}).get("discharge_summary", {}) or {}).get("layout")
        if layout == "corporate":
            exp["patient"]["phone"] = None
        gts[g["patient_id"]] = exp

    per_patient, all_checks, misses = {}, [], []
    for pid, exp in gts.items():
        path = os.path.join(a.claims, f"{pid}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            got = json.load(f)
        checks = grade_patient(got, exp)
        per_patient[pid] = checks
        all_checks += checks
        misses += [(pid, *c) for c in checks if not c[1]]

    if not all_checks:
        sys.exit("No claim outputs found to grade.")

    t = Table(title="Extraction Accuracy Scorecard")
    t.add_column("Patient")
    t.add_column("Fields OK", justify="right")
    t.add_column("Accuracy", justify="right")
    for pid, checks in sorted(per_patient.items()):
        ok = sum(1 for c in checks if c[1])
        t.add_row(pid, f"{ok}/{len(checks)}", f"{100*ok/len(checks):.0f}%")
    C.print(t)

    groups = {}
    for field, ok, *_ in all_checks:
        g = group_of(field)
        groups.setdefault(g, [0, 0])
        groups[g][1] += 1
        groups[g][0] += 1 if ok else 0
    g_t = Table(title="By Field Group")
    g_t.add_column("Group")
    g_t.add_column("Accuracy", justify="right")
    for g, (ok, tot) in sorted(groups.items()):
        g_t.add_row(g, f"{100*ok/tot:.1f}%  ({ok}/{tot})")
    C.print(g_t)

    total_ok = sum(1 for c in all_checks if c[1])
    C.print(f"\n[bold]OVERALL FIELD ACCURACY: "
            f"{100*total_ok/len(all_checks):.1f}%[/bold]  "
            f"({total_ok}/{len(all_checks)} checks)\n")

    if misses:
        m = Table(title=f"Misses ({len(misses)})")
        m.add_column("Patient"); m.add_column("Field")
        m.add_column("Got"); m.add_column("Expected")
        for pid, field, _, got_v, exp_v in misses[:25]:
            m.add_row(pid, field, str(got_v)[:40], str(exp_v)[:40])
        C.print(m)


if __name__ == "__main__":
    main()
