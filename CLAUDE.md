# CLAUDE.md — ClaimBridge project context

## What this is

ClaimBridge is an AI middleware that converts messy Indian hospital documents
(discharge summaries, bills, lab reports — PDFs, scans, photos) into validated,
ICD-10/SNOMED-coded, FHIR R4 claim bundles for India's National Health Claims
Exchange (NHCX). Target users: claims desks at 50-300 bed private hospitals on
legacy HMIS software. Solo founder project (Aviral), aiming at NHA hackathons
(next cycle ~Q1 2027), pilot hospitals, and eventually TPA/HMIS-vendor channels.

One-line pitch: hospitals can't produce the strict FHIR format NHCX demands —
their data lives in PDFs and old databases. We're the on-ramp.

## Architecture (all working, phases 0-4 complete)

```
documents/scans ──► extraction (LLM, vision for scans) ──► intermediate JSON
Bahmni MySQL   ──►  (schema.py contract, Pydantic)         (claims_out/*.json)
     ▲                        │
 MCP server                   ▼
(mcp_server.py)      coding: fuzzy retrieval over local ICD-10/SNOMED lists
                     → LLM SELECTS from candidates (never free-generates)
                              │
                              ▼
                     validator.py: 20+ rules (mandatory fields, date sanity,
                     billing math, dx↔procedure consistency, confidence flags)
                     → PASS / REVIEW / FAIL
                              │
                              ▼
                     fhir_builder.py: DETERMINISTIC JSON→FHIR R4 bundle
                     (no LLM — LLMs writing raw FHIR was rejected by design)
                              │
                              ▼ (Phase 5, blocked on ABDM sandbox access)
                     NHCX sandbox submission
```

## Repo layout

- `extraction/` — the engine
  - `schema.py` — Pydantic intermediate claim schema (the contract; extraction
    targets THIS, never FHIR directly)
  - `llm.py` — provider-agnostic (gemini | anthropic | openai | mock via
    LLM_PROVIDER env; raw REST, deliberately no vendor SDKs/frameworks)
  - `extractor.py` — extraction w/ validation-error retry; prompt rules matter
    (procedures ≠ treatments; never merge bill rows; null over invention)
  - `coder.py` — retrieval-based coding; blended fuzzy scorer (token_set +
    token_sort, case-normalized); DIRECT_ASSIGN_SCORE=96; LLM self-reports
    selection confidence; starter code lists in `codes/` (replace with full
    ICD-10 + NRCeS SNOMED before demos)
  - `validator.py`, `fhir_builder.py`, `bundle.py` — Phase 3
  - `pipeline.py` + `evaluate.py` — batch runner + accuracy grader vs
    ground_truth.json (THE quality gate — run after every prompt/logic change)
  - `api.py` — FastAPI backend (demo auth: DEMO_USERS, password claims123)
  - `app.py` — legacy Streamlit UI (superseded by React, kept for quick demos)
  - `mcp_server.py`, `load_patients.py` — Phase 1 Bahmni/OpenMRS data layer
- `frontend/` — React (Vite): landing page, login, console (Dashboard /
  UploadFlow / ReviewScreen). Design tokens in `src/styles.css`: paper #F7F9FA,
  ink #14273D, teal #0E7C66 actions, amber #C67B1F EXCLUSIVELY for
  "human attention needed", mono (IBM Plex Mono) for codes/money/IDs.
  Signature element: confidence-annotated fields (amber under 0.85).
- `test_corpus/` — 8 synthetic patients, 24 clean PDFs + 6 degraded scans,
  4 Indian hospital layouts + `ground_truth.json` labels
  (regenerate/extend: `generate_corpus.py`)

## Current measured state (don't regress this)

- Clean documents: 100.0% field accuracy (160/160), ICD 8/8, SNOMED 4/4
- Degraded scans: 100.0% (vision path)
- ~20s per claim. Validation engine catches sabotage (broken totals, impossible
  dates, missing policy) and flagged a phantom procedure the evaluator missed.
- ALWAYS rerun `pipeline.py` + `evaluate.py` on the corpus after touching
  prompts, coder logic, or schema. Accuracy is the product's moat.

## Key design decisions (do not casually reverse)

1. Extraction → intermediate schema → deterministic FHIR. Never LLM→FHIR.
2. Coding by retrieval-then-select. The LLM may only pick from real codes
   fetched from official lists. Confidence flows to UI/validator.
3. Provider-agnostic, framework-free (no LangChain). Benchmarkability matters:
   "we tested N models, here are numbers" is a pitch asset.
4. Human-in-the-loop is a feature, not a limitation. REVIEW state + amber UI.
5. MCP server isolates hospital-specific data access; swapping hospitals means
   rewriting 4 tool implementations, nothing else.
6. Evaluator is ground truth. If evaluator and pipeline disagree, investigate
   both — each has caught the other's bugs.

## Environment / running

- Windows, miniconda Python. Env vars per terminal (or run_test.bat):
  LLM_PROVIDER=gemini, GEMINI_API_KEY=..., poppler on PATH (pdf2image).
- Engine: `python pipeline.py --docs-dir <corpus/documents> --out claims_out`
  then `python evaluate.py --claims claims_out --ground-truth <ground_truth.json>`
- Full app: `uvicorn api:app --port 8000` (in extraction/) +
  `npm run dev` (in frontend/) → http://localhost:5173
- Bahmni (fake hospital) via docker compose in bahmni-docker/bahmni-lite;
  MySQL exposed on 3306; openmrs-user/password. CAUTION: never `set
  OPENMRS_DB_HOST` in a terminal that will run docker compose (env leaks into
  containers — caused a real outage once).

## Roadmap / open items

- Phase 5 (NEXT, blocked): NHCX sandbox submission client. Blocked on ABDM
  sandbox access — application rejected for personal email; needs domain +
  org email + reapplication at sandbox.abdm.gov.in. Study open-source HCX
  protocol SDKs (hcx-integrator-sdk on GitHub) before building.
- Replace starter code lists with full ICD-10 (WHO/CMS) and SNOMED via NRCeS.
- Phone-photo stress test (print corpus docs, photograph badly, measure).
- Real-auth (JWT, users) to replace demo auth. Multi-tenancy.
- Demo video (3 min), README polish, repo public for hackathons.
- Watch abdm.gov.in for next NHA hackathon cycle (announce ~Dec 2026-Feb 2027,
  registration windows are SHORT — ~2 weeks).

## Conventions

- Keep diffs small and targeted; the human reviews via `git diff`.
- After engine changes: run the corpus benchmark before declaring done.
- Amber in UI means exactly one thing. Don't dilute it.
- Honest numbers only: never claim accuracy beyond what evaluate.py printed,
  and always name the benchmark's scope (8 synthetic patients).