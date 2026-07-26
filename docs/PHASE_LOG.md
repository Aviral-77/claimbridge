# ClaimBridge — Phase-by-Phase Build Log

A running journal of the scalability migration (see `ARCHITECTURE.md` for the
overall plan). Each entry records **what was built, why, and the gotchas** — so
anyone picking this up later has the reasoning, not just the diff.

---

## Phase A1 — Infra scaffold (docker-compose + Dockerfile)

**Goal:** stand up the backing services the scalable architecture needs
(Postgres, Redis, MinIO) plus the FastAPI api, entirely locally. No AWS, no cost.

**Files added:**
- `extraction/requirements.txt` — dependencies were previously implicit (conda
  env only). Reverse-engineered from imports, split into *current runtime* vs
  *Phase A infra clients* (SQLAlchemy/psycopg/alembic/celery/redis/boto3).
  Installing the infra clients now means the image builds once, not per-phase.
  `streamlit` (legacy `app.py`) deliberately excluded to keep the image lean.
- `extraction/Dockerfile` — `python:3.12-slim` + `poppler-utils` (the container
  version of "poppler on PATH"; `pdf2image` shells out to it). requirements
  copied before source so the pip layer caches. One image serves both API and
  (later) Celery worker — the worker just overrides `command`.
- `extraction/.dockerignore` — keeps `app_data/`, `__pycache__`, etc. out of the
  build context.
- `docker-compose.yml` — postgres + redis + minio + minio-init (bucket creator)
  + api. Key decisions:
  - **Health checks + `depends_on: service_healthy`** so the api waits for the
    DB/Redis to actually accept connections (avoids boot races).
  - **MinIO, not real S3** — S3-compatible, so the same storage code works
    local→AWS unchanged. That's the whole reason to use it in dev.
  - Every value has a `${VAR:-default}` → runs with zero config, all overridable.
  - api container already receives `DATABASE_URL`/`REDIS_URL`/`S3_*` (before the
    code reads them) so A2–A4 are pure code changes, no compose edits.
  - `./extraction` bind-mounted with `--reload` → live code reload in dev.
  - Worker service written but **commented out** (enabled in A4 once `tasks.py`
    exists) so `up` works today.
- `.env.docker.example` + `.gitignore` update. **Gotcha:** the repo's existing
  `.env` uses Windows-batch syntax (`set VAR=...`), which Compose can't parse.
  Fix: a separate dotenv `.env.docker`, loaded via
  `docker compose --env-file .env.docker up` (that flag makes Compose ignore the
  batch `.env`). `.env.docker` is gitignored (holds the real Gemini key).

**Run:** `cp .env.docker.example .env.docker` (add key) →
`docker compose --env-file .env.docker up --build`. API on :8000, MinIO console
on :9001, Postgres on :5432.

**State after A1:** infrastructure is up; the api container *runs* but still uses
the old filesystem code paths. A2/A3 are where the app starts *using* Postgres
and MinIO. Validated with `docker compose config` (passes).

---

## Phase A2 — Database layer (SQLAlchemy + Postgres)

**Goal:** replace the `app_data/*.json` filesystem state (claims, validations,
bundles) with a real database, so multiple app instances can share state and the
Dashboard/Claims lists become indexed queries instead of `os.listdir()` + JSON
parsing.

**Files added:**
- `extraction/models.py` — SQLAlchemy 2.0 ORM. Two tables:
  - `Claim` — the human id (`CB-…`) is the PK. Full payloads (`extraction`,
    `validation`, `bundle`) stored as **JSON columns**; the list-view fields
    (`patient_name`, `uhid`, `amount`, `flags`, `status`) are **denormalized**
    onto indexed columns so the dashboard is one query. Carries a
    `hospital_id` (default `"demo"`) as the multi-tenancy hook for A7, plus
    `created_at`/`updated_at`, `seconds`, `error`. A `summary()` method returns
    exactly the shape the old `_summary()` produced (frontend unchanged).
  - `Document` — per-file metadata (filename, content_type, size, `storage_key`
    for A3), FK to Claim with cascade delete.
  - Blob columns use **JSONB on Postgres** (binary, GIN-indexable — the scalable
    type) via `JSON().with_variant(JSONB, "postgresql")`, falling back to plain
    JSON only on SQLite (tests). String/Float for the rest.
- `extraction/db.py` — engine + `SessionLocal` + `get_db()` FastAPI dependency +
  `init_db()`. **Postgres is the store: `DATABASE_URL` is required and the app
  fails fast if unset** — no silent fallback to a non-scalable store. SQLite is
  supported *only* when a test explicitly passes a `sqlite://` URL. Connection
  pool sized (`pool_size=10, max_overflow=20`) for concurrent API + worker load;
  `pool_pre_ping=True` recycles dropped connections.

  > **Correction (post-review):** an earlier draft silently defaulted to a local
  > SQLite file when `DATABASE_URL` was unset. SQLite is single-writer and can't
  > back a multi-instance deployment, so that was a foot-gun — removed. Postgres
  > is the only runtime store; SQLite is test-only.

**Files changed:**
- `extraction/api.py` — every endpoint moved from JSON files to DB queries via a
  `db: Session = Depends(get_db)` dependency:
  - `list_claims` → `SELECT … ORDER BY updated_at DESC`.
  - `get_claim` → `db.get(Claim, cid)`.
  - `create_claim` → runs the **unchanged** pipeline, then upserts the Claim row
    (extraction/validation/status/denormalized fields) + replaces Document rows.
  - `update_claim` / `approve` → mutate the row, re-validate / build+store the
    FHIR bundle as JSON, set `approved`.
  - `bundle` download → serialize the stored JSON.
  - `startup` hook calls `init_db()` (Alembic migrations replace `create_all`
    later).
  - Demo auth (`DEMO_USERS`/`_TOKENS`) untouched — that's A7.

**Deliberately deferred to A3:** uploaded document *bytes* still write to
`app_data/uploads/{cid}` and the preview endpoint still reads from disk. Only the
*metadata* is in the DB now (with a `storage_key` column waiting for S3).

**Untouched (by design):** the engine modules and `pipeline.py`/`evaluate.py` —
they operate on files directly and remain the accuracy gate.

**Verified (no Docker needed):** in-memory SQLite smoke test — tables create,
Claim + Document insert, `summary()` and the relationship load correctly; and
`api.py` imports with all 9 routes registered.

### A2 addendum — Alembic migrations + logging

**Alembic (schema is now versioned, not `create_all`):**
- `extraction/alembic.ini` — URL is injected from `DATABASE_URL` at runtime (not
  hardcoded), so the same config works local + docker.
- `extraction/alembic/env.py` — targets `models.Base.metadata` (so
  `--autogenerate` diffs against the ORM), reads `DATABASE_URL`, supports offline
  (`--sql`) and online modes, `compare_type=True`.
- `extraction/alembic/versions/0001_initial.py` — hand-written initial migration
  matching the compiled DDL (claims + documents, JSONB blobs, indexes, FK
  cascade). down-revision handles clean teardown.
- `db.py init_db()` now **only** `create_all`s on SQLite (tests); on Postgres the
  schema is owned by Alembic. The docker api `command` runs
  `alembic upgrade head && uvicorn …` (idempotent) so migrations apply on start.
- To evolve the schema later: edit `models.py` →
  `alembic revision --autogenerate -m "..."` → review → `alembic upgrade head`.

**Logging (one rotating file per component):**
- `extraction/logging_setup.py` — `get_logger("api")` writes to console **and**
  `logs/api.log`; each component gets its own file (`api.log`, `db.log`, and
  `storage.log`/`tasks.log` in later phases). Rotating at ~2 MB × 5 backups.
  `LOG_DIR` / `LOG_LEVEL` env-overridable; idempotent (no duplicate handlers).
- Instrumented `db.py` (engine creation with **password-masked** URL, schema
  mode) and every `api.py` endpoint (entry, key ids, warnings on 404/401/409,
  `log.exception` on pipeline failure, and per-stage logs in `create_claim`:
  reading docs → extract → code → validate → persist).
- `logs/` added to `.gitignore` and `.dockerignore`.
- *(Scope note: logging was added to the service layer we own — api/db and the
  upcoming storage/tasks. The engine modules were left untouched to protect the
  accuracy benchmark; easy to extend there on request.)*

**Verified:** `logs/api.log` + `logs/db.log` are created and written on import;
migration + `env.py` compile; JSONB DDL confirmed on the Postgres dialect. (Full
`alembic upgrade head` runs in the container, where alembic is installed.)

---

## Phase A3 — Object storage (S3 / MinIO)

**Goal:** move document *bytes* off the local filesystem into object storage, so
any app/worker instance can read them and the last `app_data` dependency is gone.

**Files added:**
- `extraction/storage.py` — thin boto3 wrapper. `put_bytes`/`get_bytes`/
  `presigned_get_url`/`ensure_bucket`, keyed `claims/{cid}/documents/{filename}`.
  Client is built lazily (boto3 doesn't connect until a call), so importing the
  app on a host without boto3 still works. Same code hits MinIO locally
  (`S3_ENDPOINT_URL` set) and real S3 in prod (endpoint unset).

**Files changed:**
- `extraction/api.py`:
  - `create_claim` uploads each file to storage (`put_bytes`) and records the
    `storage_key` on the Document row — no disk writes.
  - `doc_preview` looks the document up by (claim_id, filename) in the DB, pulls
    bytes from storage, and renders/streams. Bonus: **no path-traversal surface**
    anymore — the filename is a DB lookup, not a filesystem path.
  - startup calls `storage.ensure_bucket()` (best-effort).
  - `Document.storage_key` (the column reserved in A2) is now populated.
- **`app_data/uploads` is retired** — documents live in the object store.

**Note:** the FHIR **bundle** stays in the DB (`claims.bundle` JSONB), not S3 —
it's small structured JSON that's useful to keep queryable and serve directly.
S3 is for the large binary scans. `presigned_get_url` exists for real-S3 direct
download in prod; locally the preview endpoint *streams* bytes because the
`minio` hostname isn't resolvable from the browser.

---

## Phase A4 — Celery task queue

**Goal:** run the ~20s extract→code→validate pipeline **off the API process**, on
a worker, via a Redis-backed queue.

**Files added:**
- `extraction/tasks.py` — Celery app (`celery_app`, Redis broker + result
  backend) + the `process_claim` task. The task: sets the claim `RUNNING`, reads
  each document's bytes from storage, runs the **unchanged** engine
  (extract→code→validate), writes results + denormalized fields + `seconds` back
  to the DB, and sets status to the validator result. On exception it records
  `status=FAIL` + `error` and re-raises. Heavy imports (engine, pypdf, pdf2image)
  are lazy inside the task so the worker boots fast.

**Files changed:**
- `extraction/api.py` `create_claim` — now: upload files to storage → insert the
  claim as `QUEUED` → `process_claim.delay(cid)`. The pipeline no longer runs in
  the API process.
- `docker-compose.yml` — the **worker service is enabled**
  (`celery -A tasks.celery_app worker -c 4`, prefork pool = CPU parallelism for
  scan rendering). Runs in the Linux container, not the Windows host (prefork is
  flaky on Windows).

**Deliberate intermediate:** the API still **blocks on the task result**
(`async_result.get()`, run in a threadpool so it doesn't stall the event loop)
and returns the final `{id, seconds, status}`. This keeps the frontend contract
unchanged — the app keeps working — while execution has actually moved to the
worker. **Phase A5** removes the blocking wait (return `202` + QUEUED, poll for
status); **A6** updates the frontend to poll. So the sync wait is a stepping
stone, not the end state.

**New status values:** `QUEUED` / `RUNNING` now exist (set by the API on enqueue
and the worker on start). Because the API currently blocks until done, the
frontend only ever sees the terminal status — the transient states become
visible once A5/A6 land.

**Verified:** `docker compose config` passes with the worker enabled;
`storage.py`/`tasks.py`/`api.py` compile; `api.py` imports on the host with all 9
routes (storage/celery stay lazy). Full worker run (Redis + real task execution)
happens in the container — `logs/tasks.log` will show the per-stage trace.

---

## Phase A5 — Thin async API + A6 — Frontend status polling

**Goal:** remove the blocking wait from A4 so the API returns immediately, and
make the frontend poll for progress — the true non-blocking async flow.

**A5 — `extraction/api.py`:**
- `create_claim` now `@app.post(..., status_code=202)`: uploads files → inserts
  the claim as `QUEUED` → `process_claim.delay(cid)` → **returns right away**
  `{id, status: "QUEUED", task_id}`. No `.get()`, no threadpool wait — the web
  worker is free the instant the upload is stored.
- New `GET /api/claims/{cid}/status` — a lightweight polling endpoint returning
  just `{id, status, seconds, flags, error}` (no heavy extraction payload).
  Logged at DEBUG so 2s polling doesn't spam `api.log`.

**A6 — frontend:**
- `frontend/src/api.js` — added `claimStatus(id)` → `GET …/status`.
- `frontend/src/components/UploadFlow.jsx` — `process()` now awaits the 202, then
  **polls `claimStatus` every 2s** (`poll()` with a `pollRef` timeout, cleared on
  unmount). Terminal handling: `PASS`/`REVIEW` → stepper `done` + "Open review";
  `FAIL` with an `error` (worker crash) → `failed` + Retry; validation `FAIL`
  (no error) → `done`/reviewable. Tolerates transient fetch errors (~5 misses
  before giving up). The existing `ProcessingStepper` animates while polling and
  resolves when the real status turns terminal — no stepper changes needed.

**Result — the async flow is now real:** upload → `202 QUEUED` → worker picks it
up (`RUNNING`) → `PASS/REVIEW/FAIL` → the UI reflects each transition live via
polling. `QUEUED`/`RUNNING` are finally user-visible. The API process never runs
the pipeline; a slow/large claim no longer ties up a web worker.

**Verified:** `api.py` compiles + imports with the new `…/status` route (10
routes); `npm run build` passes (42 modules, no errors).

---

### Live-run fix — worker module imports

First real `docker compose up` surfaced a bug: the Celery worker raised
`ModuleNotFoundError: No module named 'storage'`. Cause: the `celery` console
script does not put the working dir on `sys.path` the way `uvicorn api:app`
does, so the worker's lazy imports (`storage`, and next the engine modules)
couldn't be found — even though `api.py`'s `sys.path.insert(0, HERE)` made the
API side work. Fixed two ways (belt + suspenders):
- `tasks.py` now does `sys.path.insert(0, HERE)` at module top (mirrors api.py).
- `docker-compose.yml` sets `PYTHONPATH=/app` on the **api** and **worker**
  services, so local imports resolve regardless of Celery's path handling.

Gotcha noted: a plain `docker compose restart worker` did **not** reload changed
code / env — use `docker compose up -d --force-recreate api worker`. Also every
compose command needs `--env-file .env.docker` (or `set COMPOSE_ENV_FILES=
.env.docker`) or Compose chokes on the Windows-batch `.env`.

**Live verification:** upload of the P001 corpus (3 PDFs) → `202 QUEUED` → worker
`RUNNING` → **`PASS` in 17.6s** (flags 0), status observed transitioning via
polling. Full async path confirmed on real infra.

### Task tracking (job id + stage + API + log)

Made async jobs first-class so a `task_id` is trackable end to end.
- **DB (migration `0002_task_tracking`):** added `claims.task_id` (indexed) and
  `claims.stage` (queued | reading | extracting | coding | validating | done |
  failed). `Claim.job()` returns the task-tracking view.
- **Worker (`tasks.py`):** task is now `bind=True`; records `self.request.id` on
  the claim and calls `set_stage(...)` at each pipeline step, committing so
  pollers see live progress.
- **API (`api.py`):** `create_claim` persists `task_id` + `stage="queued"` on
  enqueue. New endpoints: `GET /api/tasks` (all jobs, newest first) and
  `GET /api/tasks/{task_id}` (one job: DB status/stage + best-effort Celery
  `AsyncResult` state). `/api/claims/{cid}/status` now also returns `stage` +
  `task_id`.
- **Log:** a dedicated **`logs/jobs.log`** (logger `jobs`, written by both api and
  worker) records the lifecycle: `task=<id> claim=<cid> stage=<stage>` from
  `queued` through `done`/`failed`.

Apply: `docker compose up -d --force-recreate api worker` (api runs
`alembic upgrade head` → applies 0002; worker picks up new code).

## Phase A7 — JWT auth + multi-tenancy

**Goal:** replace the demo auth (`DEMO_USERS` + in-memory `_TOKENS` dict) with
real identity and per-hospital data isolation. The in-memory token dict was also
a scaling bug — a token issued by one API instance wasn't known to another;
stateless JWTs fix that.

**Files added:**
- `extraction/auth.py` — bcrypt password hashing, JWT create/decode
  (`PyJWT`, HS256, 12h, `JWT_SECRET` from env), a `get_current_user` dependency
  (`Authorization: Bearer`), a `user_from_query_token` for media endpoints, and
  an idempotent `seed_demo()` (same demo emails/password as before).
- `alembic/versions/0003_auth.py` — `hospitals` + `users` tables.

**Files changed:**
- `models.py` — `Hospital` and `User` (email unique, bcrypt `password_hash`,
  `hospital_id` FK, role). (`claims.hospital_id` existed since A2.)
- `api.py` — `login` verifies against the `users` table and issues a JWT; every
  claim/task endpoint now requires `current_user` and is **scoped by
  hospital_id** via `_owned_or_404` (cross-tenant reads 404, not 403 — don't
  leak existence). `create_claim` stamps the caller's `hospital_id`. `bundle` and
  `preview` (browser `<a>`/`<img>`, no header) authenticate via `?token=`.
  `startup` runs `seed_demo`.
- `frontend/src/api.js` — sends `Authorization: Bearer <jwt>` (read from the
  saved session) on every call; media URLs append `?token=`.
- `docker-compose.yml` — `JWT_SECRET` on the api service.
- `requirements.txt` — `PyJWT`, `bcrypt`.

**Verified (SQLite round-trip):** bcrypt verify (good→True, bad→False); JWT
decode + tamper→None; `seed_demo` idempotent (2 hospitals, 2 users); tenant
isolation (skn query returns only skn claims). `api.py` imports (12 routes);
compose valid; `npm run build` passes.

**Apply:** requirements changed, so rebuild —
`docker compose up -d --build api worker` (api runs `alembic upgrade head` →
0003, then seeds demo users). Login unchanged for the user: `desk@skn.hospital` /
`claims123` (hospital **skn**) or `admin@lifecare.in` / `claims123` (**lifecare**).
Note: claims created before A7 are under the `demo` tenant and won't show for
these users — re-upload to see them under `skn`.

## Phase A — status: COMPLETE (local)

All state decoupled from the API process: **Postgres** (claims/validations/users),
**S3/MinIO** (documents), **Celery + Redis** (async pipeline), non-blocking API +
polling frontend, **JWT auth + per-hospital multi-tenancy**, Alembic migrations,
per-component file logging, task tracking. Runs entirely via
`docker compose --env-file .env.docker up --build`. Engine + benchmark
(`pipeline.py`/`evaluate.py`) untouched. **Next: Phase B** (deploy to AWS) — see
`ARCHITECTURE.md`.
