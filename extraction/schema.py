"""The intermediate claim schema — the contract between extraction and everything else.

Design rule: extract to THIS, not to FHIR. Simple, flat-ish, validatable.
FHIR assembly (Phase 3) consumes this deterministically.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class PatientInfo(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = Field(None, description="Male/Female/Other")
    uhid: Optional[str] = None
    abha: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class Encounter(BaseModel):
    ip_number: Optional[str] = None
    admission_datetime: Optional[str] = Field(None, description="ISO 8601 if possible")
    discharge_datetime: Optional[str] = None
    department: Optional[str] = None
    consultant: Optional[str] = None


class Diagnosis(BaseModel):
    text: str = Field(..., description="Diagnosis exactly as written in the document")
    icd10_code: Optional[str] = Field(None, description="Filled by the coding step, not extraction")
    icd10_display: Optional[str] = None
    coding_confidence: Optional[float] = None


class ProcedureInfo(BaseModel):
    text: str
    date: Optional[str] = None
    snomed_code: Optional[str] = None
    coding_confidence: Optional[float] = None


class LabResult(BaseModel):
    test: str
    result: Optional[str] = None
    unit: Optional[str] = None
    ref_range: Optional[str] = None
    flag: Optional[str] = None


class BillItem(BaseModel):
    description: str
    detail: Optional[str] = None
    amount: Optional[float] = None
    gst_percent: Optional[float] = 0


class Billing(BaseModel):
    line_items: List[BillItem] = []
    sub_total: Optional[float] = None
    gst_total: Optional[float] = None
    grand_total: Optional[float] = None


class Coverage(BaseModel):
    insurer: Optional[str] = None
    policy_number: Optional[str] = None
    tpa: Optional[str] = None
    mode: Optional[str] = Field(None, description="cashless or reimbursement")


class ClaimExtraction(BaseModel):
    """Everything needed to build a claim, extracted from one patient's documents."""
    patient: PatientInfo = PatientInfo()
    encounter: Encounter = Encounter()
    diagnoses: List[Diagnosis] = []
    procedures: List[ProcedureInfo] = []
    medications_on_discharge: List[str] = []
    labs: List[LabResult] = []
    billing: Billing = Billing()
    coverage: Coverage = Coverage()

    # provenance / quality
    source_documents: List[str] = []
    extraction_notes: Optional[str] = None


def schema_for_prompt() -> str:
    """Compact JSON-shape description embedded in the extraction prompt."""
    return ClaimExtraction(
        patient=PatientInfo(name="string", age=0, gender="Male|Female", uhid="string",
                            abha="string or null", phone="string", address="string"),
        encounter=Encounter(ip_number="string", admission_datetime="YYYY-MM-DDTHH:MM:SS",
                            discharge_datetime="YYYY-MM-DDTHH:MM:SS",
                            department="string", consultant="string"),
        diagnoses=[Diagnosis(text="diagnosis as written")],
        procedures=[ProcedureInfo(text="procedure as written", date="YYYY-MM-DD")],
        medications_on_discharge=["drug + dose + frequency as written"],
        labs=[LabResult(test="string", result="string", unit="string",
                        ref_range="string", flag="HIGH|LOW|NORMAL|ABNORMAL")],
        billing=Billing(line_items=[BillItem(description="string", detail="string",
                                             amount=0, gst_percent=0)],
                        sub_total=0, gst_total=0, grand_total=0),
        coverage=Coverage(insurer="string", policy_number="string", tpa="string",
                          mode="cashless|reimbursement"),
    ).model_dump_json(indent=2)
