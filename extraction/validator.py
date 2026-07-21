"""Rule-based validation engine — the pre-submission gate.

Runs BEFORE FHIR assembly/submission and produces the review report the UI
shows (green checks + amber flags). Severity model:
  FAIL   -> claim must not be submitted (missing mandatory data, broken math)
  REVIEW -> a human should confirm before submission (low confidence, unusual)
  PASS   -> check satisfied

Checks:
  M-*  mandatory fields for an NHCX institutional claim
  D-*  date sanity
  B-*  billing reconciliation
  C-*  clinical consistency (diagnosis <-> procedure compatibility)
  Q-*  extraction/coding quality flags (confidence thresholds)
"""

from datetime import datetime

CONFIDENCE_REVIEW_BELOW = 0.85

# ICD-10 prefix -> SNOMED procedure codes that are compatible (starter map;
# grows with every real claim you see. Absence of a mapping = no opinion.)
DX_PROC_COMPAT = {
    "K35": {"174041007", "80146002"},              # appendicitis -> appendectomy
    "K36": {"174041007", "80146002"},
    "K37": {"174041007", "80146002"},
    "K80": {"45595009", "38102005"},               # gallstones -> cholecystectomy
    "K81": {"45595009", "38102005"},
    "K40": {"236028004", "44558001"},              # inguinal hernia -> hernioplasty
    "K42": {"112746006"},
}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace(" ", "T"))
    except ValueError:
        return None


def validate(ext: dict) -> dict:
    checks = []

    def add(code, desc, ok, severity="FAIL", detail=""):
        checks.append({"code": code, "check": desc,
                       "result": "PASS" if ok else severity,
                       "detail": "" if ok else detail})

    p = ext.get("patient") or {}
    e = ext.get("encounter") or {}
    b = ext.get("billing") or {}
    cov = ext.get("coverage") or {}
    dxs = ext.get("diagnoses") or []
    procs = ext.get("procedures") or []

    # ---- M: mandatory fields ------------------------------------------
    add("M-01", "Patient name present", bool(p.get("name")), detail="name missing")
    add("M-02", "Patient identifier (UHID/ABHA) present",
        bool(p.get("uhid") or p.get("abha")), detail="no UHID or ABHA")
    add("M-03", "Gender present", bool(p.get("gender")), detail="gender missing")
    add("M-04", "Admission datetime present", bool(e.get("admission_datetime")),
        detail="admission missing")
    add("M-05", "Discharge datetime present", bool(e.get("discharge_datetime")),
        detail="discharge missing")
    add("M-06", "At least one diagnosis", len(dxs) > 0, detail="no diagnosis")
    add("M-07", "All diagnoses ICD-10 coded",
        all(d.get("icd10_code") for d in dxs) if dxs else False,
        detail="uncoded diagnosis present")
    add("M-08", "Insurer present", bool(cov.get("insurer")), detail="insurer missing")
    add("M-09", "Policy number present", bool(cov.get("policy_number")),
        detail="policy number missing")
    add("M-10", "Claim total present", _num(b.get("grand_total")) is not None,
        detail="grand total missing")

    # ---- D: dates -------------------------------------------------------
    adm, dis = _dt(e.get("admission_datetime")), _dt(e.get("discharge_datetime"))
    if adm and dis:
        add("D-01", "Discharge after admission", dis > adm, detail=f"{adm} !< {dis}")
        add("D-02", "Length of stay plausible (<= 60 days)",
            (dis - adm).days <= 60, severity="REVIEW",
            detail=f"LOS {(dis-adm).days} days")
    if adm:
        add("D-03", "Admission not in the future",
            adm <= datetime.now(), detail=f"admission {adm} is in the future")
    for pr in procs:
        pd = _dt(pr.get("date"))
        if pd and adm and dis:
            add("D-04", f"Procedure date within stay ({pr.get('text','')[:30]})",
                adm.date() <= pd.date() <= dis.date(), severity="REVIEW",
                detail=f"procedure {pd.date()} outside {adm.date()}..{dis.date()}")

    # ---- B: billing reconciliation --------------------------------------
    items = b.get("line_items") or []
    add("B-01", "Bill has line items", len(items) > 0, detail="no line items")
    line_sum = sum(_num(li.get("amount")) or 0 for li in items)
    sub, gst, grand = _num(b.get("sub_total")), _num(b.get("gst_total")), _num(b.get("grand_total"))
    if items and sub is not None:
        add("B-02", "Line items sum to sub-total", abs(line_sum - sub) <= 2,
            detail=f"lines={line_sum:.0f} vs sub_total={sub:.0f}")
    if sub is not None and grand is not None:
        expected = sub + (gst or 0)
        add("B-03", "Sub-total + GST equals grand total",
            abs(expected - grand) <= 2,
            detail=f"{sub:.0f}+{gst or 0:.0f} != {grand:.0f}")
    if grand is not None:
        add("B-04", "Claim amount plausible (Rs.500 - Rs.50,00,000)",
            500 <= grand <= 5_000_000, severity="REVIEW",
            detail=f"grand_total={grand:.0f}")

    # ---- C: clinical consistency ----------------------------------------
    coded_dx_prefixes = {d["icd10_code"][:3] for d in dxs if d.get("icd10_code")}
    for pr in procs:
        code = pr.get("snomed_code")
        if not code:
            continue
        opinions = [pref for pref in coded_dx_prefixes if pref in DX_PROC_COMPAT]
        if opinions:
            ok = any(code in DX_PROC_COMPAT[pref] for pref in opinions)
            add("C-01", f"Procedure consistent with diagnosis ({pr.get('text','')[:30]})",
                ok, severity="REVIEW",
                detail=f"SNOMED {code} unusual for dx prefix(es) {opinions}")
    surgical = bool(procs)
    ot_billed = any("theatre" in (li.get("description") or "").lower()
                    or "surgeon" in (li.get("description") or "").lower()
                    for li in items)
    if ot_billed:
        add("C-02", "OT/surgeon billed only when a procedure is documented",
            surgical, severity="REVIEW",
            detail="OT/surgeon charges present but no documented procedure")

    # ---- Q: quality flags -------------------------------------------------
    for d in dxs:
        conf = d.get("coding_confidence")
        if d.get("icd10_code") and conf is not None:
            add("Q-01", f"ICD coding confidence ({d['icd10_code']})",
                conf >= CONFIDENCE_REVIEW_BELOW, severity="REVIEW",
                detail=f"confidence {conf:.2f} < {CONFIDENCE_REVIEW_BELOW}")
    for pr in procs:
        conf = pr.get("coding_confidence")
        if pr.get("snomed_code") and conf is not None:
            add("Q-02", f"SNOMED coding confidence ({pr['snomed_code']})",
                conf >= CONFIDENCE_REVIEW_BELOW, severity="REVIEW",
                detail=f"confidence {conf:.2f} < {CONFIDENCE_REVIEW_BELOW}")

    fails = [c for c in checks if c["result"] == "FAIL"]
    reviews = [c for c in checks if c["result"] == "REVIEW"]
    status = "FAIL" if fails else ("REVIEW" if reviews else "PASS")
    return {
        "status": status,
        "summary": {"total_checks": len(checks), "passed":
                    sum(1 for c in checks if c["result"] == "PASS"),
                    "review_flags": len(reviews), "failures": len(fails)},
        "checks": checks,
    }
