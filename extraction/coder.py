"""Medical coding by retrieval, not generation.

Flow per diagnosis/procedure:
  1. rapidfuzz searches the local code list -> top-k candidates
  2. if the top match is near-exact, assign it directly (deterministic)
  3. otherwise the LLM picks ONE code from the candidates (never invents)
  4. confidence recorded either way

Replace the starter CSVs with full official lists when downloaded:
  ICD-10: WHO / CMS code files -> codes/icd10.csv  (columns: code,description)
  SNOMED procedures via NRCeS  -> codes/snomed_procedures.csv (code,description)
"""

import csv
import json
import os

from rapidfuzz import fuzz, process, utils


def _blend_scorer(q, c, **kwargs):
    """token_set finds containment, token_sort penalizes extra words; the blend
    stops 'Acute appendicitis' scoring 100 vs longer, more specific wrong codes."""
    return 0.5 * fuzz.token_set_ratio(q, c, **kwargs) + \
           0.5 * fuzz.token_sort_ratio(q, c, **kwargs)

HERE = os.path.dirname(os.path.abspath(__file__))

DIRECT_ASSIGN_SCORE = 96   # >= this: skip the LLM, assign top candidate
                           # (kept high: sibling codes often score 88-94 and
                           #  MUST go to the LLM for clinical judgment)
TOP_K = 8


class CodeIndex:
    def __init__(self, csv_path):
        self.entries = []          # (code, description)
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.entries.append((row["code"].strip(), row["description"].strip()))
        self.descriptions = [d for _, d in self.entries]

    def search(self, text, k=TOP_K):
        hits = process.extract(text, self.descriptions,
                               scorer=_blend_scorer,
                               processor=utils.default_process, limit=k)
        return [(self.entries[idx][0], self.entries[idx][1], score)
                for _, score, idx in hits]


def _llm_pick(llm, clinical_text, candidates, system_kind):
    cand_block = "\n".join(f"{c} | {d} | fuzzy={s:.0f}" for c, d, s in candidates)
    prompt = (
        f"Clinical text from an Indian hospital document: \"{clinical_text}\"\n\n"
        f"CANDIDATES ({system_kind}):\n{cand_block}\n\n"
        f"Pick the single best {system_kind} code for the clinical text, choosing ONLY "
        f"from the candidates above. Apply standard coding conventions:\n"
        f"- Code the PRIMARY condition described, not a secondary manifestation or "
        f"complication of it (e.g. for 'gastroenteritis with dehydration', code the "
        f"gastroenteritis, not the dehydration).\n"
        f"- When the text gives no further specification, prefer the 'unspecified' "
        f"code over 'other' or more specific variants.\n"
        f"- Do not add severity, laterality, or complications the text does not state.\n"
        f"If none fit, use the closest reasonable candidate. Also report your confidence "
        f"(0.0-1.0) that this code is the correct billing code for the text.\n"
        f'Return ONLY JSON: {{"code": "...", "confidence": 0.0}}'
    )
    raw = llm.generate(prompt)
    try:
        parsed = json.loads(raw.strip().strip("`").replace("json\n", "", 1))
        code = parsed["code"].strip()
        conf = float(parsed.get("confidence", 0.7))
    except Exception:
        return None, None
    valid = {c for c, _, _ in candidates}
    return (code, max(0.0, min(conf, 1.0))) if code in valid else (None, None)


def assign_codes(extraction, llm,
                 icd_index: CodeIndex, snomed_index: CodeIndex | None = None):
    """Mutates the ClaimExtraction in place, filling codes + confidence."""
    for dx in extraction.diagnoses:
        cands = icd_index.search(dx.text)
        if not cands:
            continue
        top_code, top_desc, top_score = cands[0]
        if top_score >= DIRECT_ASSIGN_SCORE:
            dx.icd10_code, dx.icd10_display = top_code, top_desc
            dx.coding_confidence = round(top_score / 100, 2)
        else:
            picked, conf = _llm_pick(llm, dx.text, cands, "ICD-10")
            if picked:
                desc = next(d for c, d, _ in cands if c == picked)
                dx.icd10_code, dx.icd10_display = picked, desc
                dx.coding_confidence = conf if conf is not None else 0.7

    if snomed_index:
        for proc in extraction.procedures:
            cands = snomed_index.search(proc.text)
            if not cands:
                continue
            top_code, _, top_score = cands[0]
            if top_score >= DIRECT_ASSIGN_SCORE:
                proc.snomed_code = top_code
                proc.coding_confidence = round(top_score / 100, 2)
            else:
                picked, conf = _llm_pick(llm, proc.text, cands, "SNOMED CT procedure")
                if picked:
                    proc.snomed_code = picked
                    proc.coding_confidence = conf if conf is not None else 0.7
    return extraction


def default_indexes():
    icd = CodeIndex(os.path.join(HERE, "codes", "icd10.csv"))
    snomed_path = os.path.join(HERE, "codes", "snomed_procedures.csv")
    snomed = CodeIndex(snomed_path) if os.path.exists(snomed_path) else None
    return icd, snomed
