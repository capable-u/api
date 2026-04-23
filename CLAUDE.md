# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Lint (required before finalizing changes)
ruff check .
ruff format .

# Local development bootstrap
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.core.seed_categories
uvicorn main:app --reload

# Migrations
alembic revision --autogenerate -m "describe change"
alembic upgrade head

# CI parity checks (mirrors .github/workflows/api-ci.yml)
docker build -t capable-u-api-dev .
docker build -f Dockerfile.prod -t capable-u-api-prod .
```

No automated test suite exists yet. Manual testing uses `test_main.http` (note: targets old endpoints, not authoritative).

## Architecture

**FastAPI backend** for importing bank statement PDFs, parsing transactions with an LLM, and managing duplicate detection. Multi-currency support with Celery-based async processing.

**Service boundary** is route-first:
- `app/api/*.py` — HTTP orchestration
- `app/services/*.py` — domain logic
- `app/models/*.py` — SQLAlchemy ORM
- `app/schemas/*.py` — Pydantic contracts

**Deployment topology**: separate containers for `api` (uvicorn), `worker` (Celery), `beat` (Celery Beat scheduler); `docker-compose.prod.yml` wires them with PostgreSQL and Redis.

## Core Product Loop (PDF Import)

`POST /imports` → `app/api/routes_upload.py` → Celery task (`app/worker/tasks.py`):

1. Create `ImportJob(status="uploaded")` before any heavy work
2. Extract PDF text (`app/services/pdf_extract.py`)
3. Parse via OpenAI structured JSON output capped at `MAX_MODEL_INPUT_CHARS = 12000` (`app/services/transaction_parser.py`, `app/services/llm_client.py`)
4. Validate category IDs against DB; fallback to `Other` with `CATEGORY_CONFIDENCE_PENALTY = 0.35`
5. Normalize: `currency` → uppercase, `direction` → lowercase
6. Build deterministic SHA256 fingerprint (`app/services/fingerprint.py`)
7. Detect duplicates (`app/services/duplicate_detector.py`)
8. Skip exact duplicates from insert; count as `duplicate_transactions`
9. Finalize `ImportJob` status: `done`, `needs_review`, `failed`, or `llm_failed`
10. Trigger monthly summary rebuilds

## Duplicate Detection

- **Exact**: fingerprint match → `duplicate_confirmed`, score `1.000`, reason `exact_fingerprint`
- **Probable**: amount/currency/direction + ±3 day window + text similarity ≥ 0.80 → `possible_duplicate` (combines SequenceMatcher 70% + Jaccard tokens 30%)
- **Otherwise**: `unique`

`PATCH /transactions/{id}` must rebuild fingerprint and recalculate duplicate metadata when identity fields change.

`mark-unique` and `DELETE` adjust `ImportJob` counters (`_apply_review_job_counters`, `_apply_delete_job_counters`).

## LLM Integration

- Prompt: `app/prompts/parse_transactions.txt` (German bank statement parsing)
- Strict JSON Schema mode (`response_format.type=json_schema`, `strict=True`)
- Output validated through Pydantic (`ParsedTransactionsResponse.model_validate_json`) before use
- HTTP mapping: LLM/network failures → 502; other import failures → 500

## Database & Migrations

- Never edit applied migrations — always add a new revision in `alembic/versions/`
- Keep downgrade paths valid
- SQLAlchemy naming convention centralized in `app/models/base.py`; Alembic uses `app.models.Base.metadata`
- When adding model fields: update model → create migration → update Pydantic schema

## Configuration

Settings loaded via Pydantic Settings (`app/core/config.py`). New settings must be added to both `config.py` and `.env.example`. Reference: `.env.example`.

Key vars: `DATABASE_URL` (required), `OPENAI_API_KEY` (required), `REDIS_URL` (default `redis://redis:6379/0`), `BASE_CURRENCY` (default `EUR`), `UPLOAD_DIR` (default `./data/uploads`).

## Commits & PRs

Conventional Commits enforced via commitlint + Husky. Format: `type(scope): summary` (under 100 chars). Allowed types in `.github/git-commit-instructions.md`. PR titles must match the same format.

Releases managed by Release Please; Docker images published on `main`/tags.
