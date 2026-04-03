# Copilot Instructions for `capable-u/api`

This document defines how GitHub Copilot (and contributors using Copilot) should work in this repository.
Use it as the primary implementation guide for architecture, conventions, workflow, and safety checks.

## 1) Project Overview

- **Project type**: Python FastAPI backend for importing bank statement PDFs, parsing transactions with an LLM, and managing duplicate detection.
- **Runtime entrypoint**: `main.py` (`FastAPI` app named `app`).
- **Core domain**:
  - Upload PDF statements.
  - Extract text from PDF.
  - Parse transactions via OpenAI structured JSON output.
  - Assign categories and confidence.
  - Detect exact and probable duplicates.
  - Expose endpoints to list/update/review/delete transactions.
- **Current API routers**:
  - `app/api/routes_upload.py` -> `/imports`
  - `app/api/routes_transactions.py` -> `/transactions`
  - `app/api/routes_categories.py` -> `/categories`

## 2) Tech Stack and Key Dependencies

- **Language**: Python 3.14 (Dockerfiles), CI currently validates on Python 3.12.
- **Framework**: FastAPI.
- **ORM/DB**: SQLAlchemy 2.x + Alembic migrations.
- **Database**: PostgreSQL (default in compose).
- **LLM integration**: OpenAI-compatible chat completions endpoint via `httpx`.
- **PDF parsing**: `pypdf`.
- **Linting**: `ruff`.
- **Commit quality**: Conventional Commits + `commitlint` + Husky commit hook.

See `requirements.txt`, `package.json`, `.husky/commit-msg`, `commitlint.config.mjs`.

## 3) Repository Layout (Important Paths)

- `main.py`: FastAPI app setup, CORS, router registration, `/health`.
- `app/core/config.py`: environment-backed settings (Pydantic Settings).
- `app/core/db.py`: SQLAlchemy engine/session and `get_db` dependency.
- `app/core/seed_categories.py`: idempotent category seeding.
- `app/models/*`: SQLAlchemy models (`Category`, `ImportJob`, `Transaction`, enums).
- `app/schemas/*`: Pydantic request/response schemas.
- `app/services/*`: PDF extraction, prompt/schema shaping, LLM client, fingerprinting, duplicate detector.
- `app/prompts/parse_transactions.txt`: LLM extraction prompt for German bank statement text.
- `alembic/` + `alembic.ini`: migration setup and revision history.
- `.github/workflows/`: CI, release, image publish, PR title checks.
- `Dockerfile` and `Dockerfile.prod`: development and production container builds.
- `docker-compose.prod.yml`: production-like local orchestration.

## 4) Environment Variables and Configuration

Defined by `app/core/config.py` and runtime configs:

- `DATABASE_URL` (required)
- `UPLOAD_DIR` (default `./data/uploads`)
- `OPENAI_API_KEY` (required)
- `OPENAI_MODEL` (default `gpt-5.4-mini`)
- `OPENAI_BASE_URL` (default `https://api.openai.com/v1`)

Reference values exist in `.env.example`.

### Rules for Copilot

- Never hardcode secrets or real API keys.
- Never commit values from local `.env`.
- Keep settings loaded from environment (do not bypass `Settings`).
- If adding new setting fields, update both `app/core/config.py` and `.env.example`.

## 5) Local Development Workflow

### Python setup

1. Create and activate virtual environment.
2. Install dependencies from `requirements.txt`.
3. Provide `.env` with required values.
4. Run DB migrations and seed categories.
5. Start app with Uvicorn.

Typical command sequence:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.core.seed_categories
uvicorn main:app --reload
```

### Container-based run

Use `docker-compose.yml` to run `db` + `api` with startup command that runs:

1. `alembic upgrade head`
2. `python -m app.core.seed_categories`
3. `uvicorn main:app --host 0.0.0.0 --port 8000`

## 6) Database and Migration Conventions

- SQLAlchemy metadata naming convention is defined in `app/models/base.py`.
- Alembic migration target metadata is imported from `app.models.Base` in `alembic/env.py`.

### Rules for Copilot

- For schema changes, always create a new Alembic revision; do not silently edit old applied migrations.
- Keep downgrade paths valid.
- Keep index and FK naming consistent with naming convention.
- Ensure model changes and schema changes remain synchronized.

## 7) Domain Model Semantics

### `Category`
- `id`, unique `name`, `created_at`.

### `ImportJob`
- Tracks import lifecycle and counters:
  - `status`, `total_transactions`, `new_transactions`, `duplicate_transactions`, `needs_review_count`.
- Status values align with `ImportJobStatus` enum (`uploaded`, `parsed_text`, `parsed_transactions`, `done`, `needs_review`, `failed`, `llm_failed`).

### `Transaction`
- Core transaction fields: date, amount, currency, direction, counterparty, descriptions.
- Category + confidence.
- Duplicate metadata:
  - `duplicate_status`
  - `duplicate_of_transaction_id`
  - `duplicate_reason`
  - `duplicate_score`
- Deterministic `fingerprint` used for exact duplicate matching.

### Rules for Copilot

- Preserve counter consistency (`ImportJob` counters) when adding/modifying review, mark, or delete flows.
- Keep `duplicate_status` values aligned with `DuplicateStatus` enum.
- Avoid changing semantic meaning of existing statuses without explicit migration and API updates.

## 8) API Behavior and Contracts

### `/health`
- GET health check response model: `HealthResponse`.

### `/categories`
- GET list categories ordered by `name ASC`.

### `/imports` (POST)
Flow in `upload_statement`:
1. Validate file extension is `.pdf`.
2. Save file to `UPLOAD_DIR`.
3. Create `ImportJob(status="uploaded")`.
4. Load categories; fail if empty or no `Other` category.
5. Extract PDF text.
6. Parse transactions through LLM structured output.
7. For each parsed item:
   - Validate category ID; fallback to `Other` and apply confidence penalty.
   - Normalize currency and direction.
   - Build fingerprint.
   - Detect duplicates.
   - Skip exact duplicates from insertion and increment duplicate counter.
   - Insert unique/possible duplicates.
8. Finalize counters and status (`needs_review` or `done`).
9. Map LLM/network failures to HTTP 502; other failures to HTTP 500.

### `/transactions`
- GET list with optional `duplicate_status` filter.
- GET by id (404 if not found).
- PATCH by id:
  - Supports partial update.
  - Rebuilds fingerprint and duplicate metadata when selected fields change.
- POST `/{id}/mark-unique`:
  - Resolves a possible duplicate to unique and updates job counters.
- DELETE `/{id}`:
  - Deletes transaction and updates related job counters.

### Rules for Copilot

- Keep response shape compatible with Pydantic schemas in `app/schemas`.
- Normalize `currency` to uppercase and `direction` to lowercase where applicable.
- Preserve 404 behavior for unknown transaction IDs.
- Do not remove duplicate recalculation logic from transaction updates.

## 9) LLM and Prompting Guardrails

- Prompt file: `app/prompts/parse_transactions.txt`.
- LLM call implemented in `app/services/llm_client.py` using structured JSON response format.
- JSON schema strictness is enforced by `app/services/json_schema.py`.
- Parser caps model input text at `MAX_MODEL_INPUT_CHARS = 12000`.

### Rules for Copilot

- Keep structured output strict mode when changing extraction flow.
- Keep extraction prompt focused on transaction-only parsing and category constraints.
- Validate model output through Pydantic before using it.
- Do not add prompt logic that allows category IDs outside configured category list.

## 10) Duplicate Detection Design Notes

Implemented in `app/services/duplicate_detector.py`:

- **Exact duplicate**: fingerprint equality -> `duplicate_confirmed`, score `1.000`, reason `exact_fingerprint`.
- **Probable duplicate**:
  - Candidate filtering by amount/currency/direction/date window (+/- 3 days).
  - Similarity score combines description and counterparty similarity.
  - Threshold `0.80` => `possible_duplicate` with reason `probable_similarity`.
- **Otherwise**: `unique`.

### Rules for Copilot

- Preserve deterministic fingerprint behavior (`app/services/fingerprint.py`).
- Keep matching logic transparent and explainable (`duplicate_reason`, `duplicate_score`).
- If tuning thresholds/windows, update constants and explain rationale in PR.

## 11) Code Style and Implementation Rules

- Follow existing FastAPI + SQLAlchemy style in this repository.
- Keep functions focused and avoid unnecessary abstraction.
- Prefer explicit types for public/internal helper functions.
- Keep error handling specific; map user-visible errors to correct HTTP status.
- Use Pydantic schemas for API contracts instead of ad-hoc dict shapes (except existing legacy helpers).
- Run linter before submitting changes.

### Mandatory checks before finalizing

```bash
ruff check .
docker build -t capable-u-api-dev .
docker build -f Dockerfile.prod -t capable-u-api-prod .
```

(These mirror `.github/workflows/api-ci.yml`.)

## 12) Testing Expectations

- There is no mature automated test suite committed yet.
- Keep changes small and testable.
- For behavior changes, add tests when introducing test framework files, or provide reproducible manual verification steps.
- Keep `test_main.http` aligned with real endpoints if you edit example requests.

## 13) Git, PR, and Release Workflow

- Commit messages must follow Conventional Commits.
- `commitlint` runs via Husky commit-msg hook.
- PR title must match Conventional Commit-like format (see `.github/workflows/pr-title.yml`).
- Releases are managed by Release Please (`release-please-config.json`, `.release-please-manifest.json`).
- Docker images publish from `main`/tags via `.github/workflows/docker-publish.yml`.

### Commit message guidance

- Format: `type(scope): summary`
- Keep header under 100 chars.
- Use allowed types from `.github/git-commit-instructions.md`.

## 14) Copilot Do and Do Not

### Do

- Read relevant files before changing behavior.
- Maintain backward-compatible API responses unless explicitly requested.
- Update schemas/models/migrations together when data shape changes.
- Keep production and development Dockerfiles buildable.
- Prefer minimal, surgical edits.

### Do Not

- Do not commit secrets, credentials, or local environment artifacts.
- Do not modify historical migrations already used in environments; add new revisions.
- Do not introduce breaking API contract changes silently.
- Do not bypass duplicate detection and counter maintenance logic.
- Do not add dependencies without clear need and corresponding updates.

## 15) When Adding New Features

For any significant feature, Copilot should update all relevant layers:

1. SQLAlchemy model(s)
2. Alembic migration(s)
3. Pydantic schema(s)
4. Route/service logic
5. Error handling and status codes
6. Docs/instructions (this file if conventions change)
7. Verification steps (lint/build/manual API check)

## 16) Quick Reference Commands

```bash
# Lint
ruff check .

# Run app locally (after env and migrations)
uvicorn main:app --reload

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "describe change"

# Seed categories
python -m app.core.seed_categories

# Commit lint (manual)
npx commitlint --edit .git/COMMIT_EDITMSG
```

---

If repository structure or workflow changes, keep this document updated in the same PR.
