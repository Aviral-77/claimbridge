"""Deterministic FHIR R4 bundle assembly from a ClaimExtraction JSON.

NO LLM involved — extraction JSON in, schema-valid FHIR out, every time.
Resources produced (aligned with the NHCX claim workflow set):
  Patient, Encounter, Condition (per diagnosis), Procedure (per procedure),
  Coverage, Claim (with diagnosis/procedure/item links), all wrapped in a
  Bundle (type=collection).

Honest scope note: this targets structural R4 validity + the NRCeS field
expectations we know. Exact NHCX profile conformance (their specific
StructureDefinitions, MessageHeader envelope, signing/encryption) is a
Phase 5 task against the live sandbox — by design.
"""

import uuid
from datetime import datetime

from fhir.resources.bundle import Bundle, BundleEntry
from fhir.resources.claim import (Claim, ClaimDiagnosis, ClaimInsurance,
                                  ClaimItem, ClaimProcedure)
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.condition import Condition
from fhir.resources.coverage import Coverage
from fhir.resources.encounter import Encounter
from fhir.resources.humanname import HumanName
from fhir.resources.identifier import Identifier
from fhir.resources.money import Money
from fhir.resources.patient import Patient
from fhir.resources.period import Period
from fhir.resources.procedure import Procedure
from fhir.resources.reference import Reference

ICD10 = "http://hl7.org/fhir/sid/icd-10"
SNOMED = "http://snomed.info/sct"


def _cc(system, code, display=None, text=None):
    c = Coding(system=system, code=code)
    if display:
        c.display = display
    cc = CodeableConcept(coding=[c])
    if text:
        cc.text = text
    return cc


def _iso(dt_str):
    if not dt_str:
        return None
    s = str(dt_str).strip().replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        # FHIR dateTime requires a timezone; hospital-local = IST
        return dt.isoformat() + "+05:30"
    return dt.isoformat()


def _gender(g):
    if not g:
        return "unknown"
    g = g.lower()
    return "male" if g.startswith("m") else "female" if g.startswith("f") else "other"


def build_bundle(ext: dict) -> Bundle:
    """ext = ClaimExtraction as dict. Returns a FHIR Bundle."""
    ids = {k: f"urn:uuid:{uuid.uuid4()}" for k in
           ("patient", "encounter", "coverage", "claim")}
    p, e, b, cov = (ext.get("patient") or {}), (ext.get("encounter") or {}), \
                   (ext.get("billing") or {}), (ext.get("coverage") or {})

    # ---- Patient -------------------------------------------------------
    patient = Patient(
        identifier=[Identifier(system="https://hospital.local/uhid",
                               value=p.get("uhid") or "UNKNOWN")],
        gender=_gender(p.get("gender")),
    )
    if p.get("abha"):
        patient.identifier.append(
            Identifier(system="https://healthid.abdm.gov.in", value=p["abha"]))
    if p.get("name"):
        patient.name = [HumanName(text=p["name"])]

    # ---- Encounter -----------------------------------------------------
    period = Period()
    if _iso(e.get("admission_datetime")):
        period.start = _iso(e["admission_datetime"])
    if _iso(e.get("discharge_datetime")):
        period.end = _iso(e["discharge_datetime"])
    encounter = Encounter(
        status="finished",
        class_fhir=[_cc("http://terminology.hl7.org/CodeSystem/v3-ActCode",
                        "IMP", "inpatient encounter")],
        subject=Reference(reference=ids["patient"]),
        actualPeriod=period if (period.start or period.end) else None,
    )
    if e.get("ip_number"):
        encounter.identifier = [Identifier(
            system="https://hospital.local/ip", value=e["ip_number"])]

    # ---- Conditions ----------------------------------------------------
    conditions = []
    for dx in ext.get("diagnoses") or []:
        cond = Condition(
            clinicalStatus=_cc(
                "http://terminology.hl7.org/CodeSystem/condition-clinical", "active"),
            subject=Reference(reference=ids["patient"]),
        )
        if dx.get("icd10_code"):
            cond.code = _cc(ICD10, dx["icd10_code"],
                            dx.get("icd10_display"), text=dx.get("text"))
        else:
            cond.code = CodeableConcept(text=dx.get("text") or "unknown")
        conditions.append((f"urn:uuid:{uuid.uuid4()}", cond))

    # ---- Procedures ----------------------------------------------------
    procedures = []
    for pr in ext.get("procedures") or []:
        proc = Procedure(
            status="completed",
            subject=Reference(reference=ids["patient"]),
        )
        if pr.get("snomed_code"):
            proc.code = _cc(SNOMED, pr["snomed_code"], text=pr.get("text"))
        else:
            proc.code = CodeableConcept(text=pr.get("text") or "unknown")
        if _iso(pr.get("date")):
            proc.occurrenceDateTime = _iso(pr["date"])
        procedures.append((f"urn:uuid:{uuid.uuid4()}", proc))

    # ---- Coverage ------------------------------------------------------
    coverage = Coverage(
        status="active",
        kind="insurance",
        beneficiary=Reference(reference=ids["patient"]),
    )
    if cov.get("policy_number"):
        coverage.identifier = [Identifier(
            system="https://insurer.local/policy", value=cov["policy_number"])]
    if cov.get("insurer"):
        coverage.insurer = Reference(display=cov["insurer"])

    # ---- Claim ---------------------------------------------------------
    claim = Claim(
        status="active",
        type=_cc("http://terminology.hl7.org/CodeSystem/claim-type",
                 "institutional"),
        use="claim",
        patient=Reference(reference=ids["patient"]),
        created=datetime.now().astimezone().isoformat(),
        provider=Reference(display="Hospital"),
        priority=_cc("http://terminology.hl7.org/CodeSystem/processpriority",
                     "normal"),
        insurance=[ClaimInsurance(sequence=1, focal=True,
                                  coverage=Reference(reference=ids["coverage"]))],
    )
    claim.diagnosis = [
        ClaimDiagnosis(sequence=i + 1,
                       diagnosisReference=Reference(reference=cid))
        for i, (cid, _) in enumerate(conditions)
    ] or None
    claim.procedure = [
        ClaimProcedure(sequence=i + 1,
                       procedureReference=Reference(reference=pid))
        for i, (pid, _) in enumerate(procedures)
    ] or None
    items = []
    for i, li in enumerate(b.get("line_items") or []):
        item = ClaimItem(
            sequence=i + 1,
            productOrService=CodeableConcept(text=li.get("description") or "item"),
        )
        if li.get("amount") is not None:
            item.unitPrice = Money(value=li["amount"], currency="INR")
            item.net = Money(value=li["amount"], currency="INR")
        items.append(item)
    claim.item = items or None
    if b.get("grand_total") is not None:
        claim.total = Money(value=b["grand_total"], currency="INR")

    # ---- Bundle --------------------------------------------------------
    entries = [
        BundleEntry(fullUrl=ids["patient"], resource=patient),
        BundleEntry(fullUrl=ids["encounter"], resource=encounter),
        *[BundleEntry(fullUrl=cid, resource=c) for cid, c in conditions],
        *[BundleEntry(fullUrl=pid, resource=pr) for pid, pr in procedures],
        BundleEntry(fullUrl=ids["coverage"], resource=coverage),
        BundleEntry(fullUrl=ids["claim"], resource=claim),
    ]
    return Bundle(type="collection",
                  identifier=Identifier(system="https://claimbridge.local/bundle",
                                        value=str(uuid.uuid4())),
                  timestamp=datetime.now().astimezone().isoformat(),
                  entry=entries)
