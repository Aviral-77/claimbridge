"""LLM extraction: document text/images -> validated ClaimExtraction.

Pattern: ask for JSON matching the schema, parse with Pydantic; if validation
fails, retry ONCE feeding the validation errors back. Temperature 0 throughout.
"""

import json

from pydantic import ValidationError

from schema import ClaimExtraction, schema_for_prompt

SYSTEM = (
    "You are a medical claims data extraction engine for Indian hospital documents. "
    "You read discharge summaries, bills, and lab reports and return ONLY valid JSON "
    "matching the given schema. Rules: copy values exactly as written (do not invent "
    "or infer missing data — use null); dates to ISO 8601 where determinable; amounts "
    "as plain numbers without commas or currency symbols; diagnosis and procedure text "
    "verbatim from the document. For billing line_items: one JSON item per bill table "
    "row, exactly as printed — never merge, combine, or summarize rows, even similar "
    "ones. For medications_on_discharge: use the discharge "
    "medication list if present; if the document instead has a 'TREATMENT GIVEN' or "
    "similar section listing drugs, include those drugs. Do NOT assign ICD or SNOMED "
    "codes — leave them null. For procedures: include ONLY surgical or interventional "
    "procedures actually performed (operations, endoscopies, dialysis, mechanical "
    "ventilation, and similar). Medication administration, injections, IV fluids, "
    "insulin regimens, nebulisation, oxygen support, counselling, nursing care, and "
    "monitoring are NOT procedures — those belong in medications or nowhere. If no "
    "surgical/interventional procedure occurred, procedures must be an empty list."
)


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def extract_claim(llm, patient_hint: str, doc_texts: list[str],
                  doc_images_b64: list[str]) -> ClaimExtraction:
    """One patient's documents in, one validated ClaimExtraction out."""
    docs_block = "\n\n".join(
        f"--- DOCUMENT {i+1} ---\n{t}" for i, t in enumerate(doc_texts)
    ) or "(all documents are attached as images)"

    prompt = (
        f"Patient reference: {patient_hint}\n\n"
        f"Extract all claim data from the following hospital documents"
        f"{' and the attached scanned images' if doc_images_b64 else ''}.\n\n"
        f"{docs_block}\n\n"
        f"Return ONLY JSON matching exactly this shape:\n{schema_for_prompt()}"
    )

    raw = llm.generate(prompt, images_b64=doc_images_b64 or None, system=SYSTEM)
    try:
        return ClaimExtraction.model_validate_json(_strip_fences(raw))
    except (ValidationError, json.JSONDecodeError) as e:
        # one retry with the errors shown to the model
        retry_prompt = (
            f"{prompt}\n\nYour previous output failed validation with these errors:\n"
            f"{str(e)[:1500]}\n\nReturn corrected JSON only."
        )
        raw2 = llm.generate(retry_prompt, images_b64=doc_images_b64 or None, system=SYSTEM)
        return ClaimExtraction.model_validate_json(_strip_fences(raw2))
