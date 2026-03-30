# AGENTS.md

## Project map (start here)
- Entrypoint: `main.py` wires 3 routers only: `/imports`, `/transactions`, `/categories` and `/health`.
- Service boundary is route-first: API orchestration in `app/api/*.py`, domain logic in `app/services/*.py`, DB mapping in `app/models/*.py`, contracts in `app/schemas/*.py`.
- Core product loop: ingest PDF -> extract text -> LLM structured parse -> normalize + categorize -> duplicate detection -> persist + job counters (`app/api/routes_upload.py`).

## Critical flow invariants
- `/imports` must create `ImportJob(status="uploaded")` before heavy work and always finalize status (`done`, `needs_review`, `failed`, `llm_failed`) in `app/api/routes_upload.py`.
- Category IDs from LLM are validated against DB; invalid IDs fall back to `Other` with confidence penalty (`CATEGORY_CONFIDENCE_PENALTY = 0.35`).
- Normalize `currency` to uppercase and `direction` to lowercase before fingerprinting and duplicate checks (`app/services/fingerprint.py`, `app/api/routes_upload.py`).
- Exact duplicates (same fingerprint) are skipped from insert and counted as `duplicate_transactions`; only unique/possible duplicates are inserted.

## Duplicate/review semantics
- Duplicate engine (`app/services/duplicate_detector.py`):
  - exact: fingerprint match => `duplicate_confirmed`, score `1.000`, reason `exact_fingerprint`
  - probable: amount/currency/direction + date window +/-3 days + text similarity >= `0.80` => `possible_duplicate`
- Transaction updates (`PATCH /transactions/{id}`) must rebuild fingerprint and recalculate duplicate metadata when identity fields change (`routes_transactions.py`).
- Review counters are part of behavior: `mark-unique` and `DELETE` adjust `ImportJob.new_transactions`, `duplicate_transactions`, `needs_review_count` (`_apply_review_job_counters`, `_apply_delete_job_counters`).

## LLM integration contract
- Prompt template lives in `app/prompts/parse_transactions.txt`; runtime prompt assembly in `app/services/transaction_parser.py`.
- Model output is strict JSON Schema (`response_format.type=json_schema`, `strict=True`) in `app/services/llm_client.py`.
- Schema is hardened by `make_openai_strict_schema()` and then validated with Pydantic (`ParsedTransactionsResponse.model_validate_json`).
- Parser truncates statement text to `MAX_MODEL_INPUT_CHARS = 12000`.

## Data model + migrations
- SQLAlchemy naming convention is centralized in `app/models/base.py`; keep FK/index names Alembic-compatible.
- Alembic uses `app.models.Base.metadata` (`alembic/env.py`); add new revisions instead of editing existing ones in `alembic/versions/`.
- `seed_categories` is idempotent and required for imports; it ensures `Other` exists (`app/core/seed_categories.py`).

## Local workflow that matches CI/prod
- Local bootstrap (from repo conventions): install deps, run migrations, seed categories, then `uvicorn main:app --reload`.
- CI checks only lint + image build parity (`.github/workflows/api-ci.yml`):
  - `ruff check .`
  - `docker build -t capable-u-api-dev .`
  - `docker build -f Dockerfile.prod -t capable-u-api-prod .`
- Production-like compose (`docker-compose.prod.yml`) runs `alembic upgrade head && python -m app.core.seed_categories` before server start.

## Repo-specific conventions for agents
- Keep API responses aligned with `app/schemas/*` (routes currently serialize dicts manually, e.g. `routes_transactions.py`).
- Preserve HTTP mapping: LLM/network failures => 502; other import failures => 500 (`routes_upload.py`).
- Commit messages and PR titles follow Conventional Commits (`commitlint.config.mjs`, `.husky/commit-msg`, `.github/git-commit-instructions.md`).
- Note: `test_main.http` currently targets old sample endpoints and is not authoritative for real routes.

