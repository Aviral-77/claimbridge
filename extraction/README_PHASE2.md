# Phase 2 — Extraction & Coding Engine

Documents in → validated, ICD/SNOMED-coded claim JSON out → graded against ground truth.

```
extraction/
  schema.py      the claim contract (Pydantic) — extraction must satisfy this
  llm.py         provider layer: gemini | anthropic | openai | mock
  extractor.py   LLM extraction with validation-error retry
  coder.py       retrieval-based coding (fuzzy candidates -> LLM selects)
  pipeline.py    orchestrator: per-patient documents -> claims_out/Pxxx.json
  evaluate.py    the exam: grades output vs ground_truth.json
  codes/         icd10.csv + snomed_procedures.csv (STARTER lists — see below)
```

## Setup

```cmd
pip install rapidfuzz rich python-dotenv requests pydantic pypdf pdf2image
```

Pick a provider (Gemini Flash recommended to start — free tier covers the whole corpus):

```cmd
rem Get a key at https://aistudio.google.com -> "Get API key"
set LLM_PROVIDER=gemini
set GEMINI_API_KEY=your_key_here
```

Switching providers later = changing two env vars. Nothing else.
(anthropic -> ANTHROPIC_API_KEY, openai -> OPENAI_API_KEY; override model with LLM_MODEL.)

## Run

```cmd
cd extraction

rem clean documents first:
python pipeline.py --docs-dir "C:\...\test_corpus\corpus\documents" --out claims_out

rem grade it:
python evaluate.py --claims claims_out --ground-truth "C:\...\test_corpus\corpus\ground_truth.json"

rem vision stress test (scanned variants; needs poppler installed):
python pipeline.py --docs-dir "C:\...\corpus\documents" --scans-dir "C:\...\corpus\documents_scanned" --prefer-scans --out claims_scanned
python evaluate.py --claims claims_scanned --ground-truth "C:\...\ground_truth.json"
```

Run per-patient while iterating: `--patients P001` (fast, cheap).

## No API key? Test the plumbing with the oracle mock

```cmd
set LLM_PROVIDER=mock
set GT_PATH=C:\...\test_corpus\corpus\ground_truth.json
python pipeline.py --docs-dir ... --out claims_mock
```

The mock answers from ground truth — it proves the pipeline/grader wiring,
NOT model quality. Its coding numbers are meaningless (it picks the first
candidate instead of judging). Real accuracy numbers require a real provider.

## The two numbers that matter

After a real-provider run, evaluate.py gives you:
1. OVERALL FIELD ACCURACY — your pitch number
2. CODING (ICD-10) accuracy — your moat number

Iterate on prompts (extractor.py SYSTEM), retrieval (coder.py), and thresholds
until these plateau. Track runs in a simple log — model, date, both numbers.

## Upgrading the code lists (do before demos)

The bundled CSVs are ~50-entry starters covering the corpus. For real coverage:
- ICD-10: download the WHO/CMS full code list, save as codes/icd10.csv
  with columns code,description (~70k rows — rapidfuzz handles it fine)
- SNOMED: India has a free national license via NRCeS (nrces.in) — extract
  the procedure hierarchy to codes/snomed_procedures.csv

## Design notes (why it's built this way)

- Extraction targets the intermediate schema, never FHIR directly. Phase 3
  converts schema -> FHIR deterministically. LLMs writing raw FHIR = endless
  subtle validation failures.
- Coding is retrieval-then-select: the LLM can only choose from real codes
  fetched from the official list — it cannot hallucinate a code. Confidence
  scores flow to the review UI (Phase 4) to decide what a human must check.
- Everything is provider-agnostic and framework-free on purpose: fewer moving
  parts, benchmarkable, and the "we tested N models, here are the numbers"
  slide falls out of evaluate.py for free.
