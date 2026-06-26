# Capable-U API

A FastAPI backend for importing bank statement PDFs, parsing transactions with an LLM, and managing personal finances with multi-currency support.

## Features

- **PDF import** — upload bank statements; text is extracted and parsed by OpenAI into structured transactions
- **Duplicate detection** — exact fingerprint matching and probabilistic text similarity with a configurable threshold
- **Multi-currency** — automatic exchange rate sync from [Frankfurter](https://www.frankfurter.app/), base-currency normalization for all transactions
- **Monthly summaries** — income/expense aggregates per month, currency, and category; rebuilt incrementally on every change
- **Async processing** — Celery workers handle long-running imports; real-time status via Server-Sent Events
- **Category management** — CRUD for user-defined categories with hex colors; protected system category `Other`

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.135, Uvicorn |
| Database | PostgreSQL 16, SQLAlchemy 2, Alembic |
| Task queue | Celery 5, Redis 7 |
| LLM | OpenAI (strict JSON schema mode) |
| PDF parsing | PyPDF |
| Validation | Pydantic v2 |
| Linting | Ruff |
| CI/CD | GitHub Actions, Release Please |
| Containers | Docker, docker-compose |

## Architecture

```
app/api/          HTTP orchestration (routes)
app/services/     Domain logic
app/models/       SQLAlchemy ORM
app/schemas/      Pydantic contracts
app/worker/       Celery tasks and beat schedule
app/prompts/      LLM prompt files
```

**Deployment topology** (production): three containers — `api` (Uvicorn), `worker` (Celery), `beat` (Celery Beat) — backed by PostgreSQL and Redis.

### PDF Import Pipeline

`POST /imports` → Celery task:

1. Save `ImportJob` with status `uploaded`
2. Extract PDF text (PyPDF)
3. Truncate to `MAX_MODEL_INPUT_CHARS = 12 000` and call OpenAI in strict JSON schema mode
4. Validate category IDs; fall back to `Other` with a `0.35` confidence penalty
5. Normalize: `currency` → uppercase, `direction` → lowercase
6. Build a deterministic SHA-256 fingerprint per transaction
7. Detect exact and probable duplicates
8. Insert only non-exact-duplicate transactions
9. Set final job status: `done`, `needs_review`, `failed`, or `llm_failed`
10. Rebuild monthly summaries

### Duplicate Detection

| Type | Condition | Result |
|------|-----------|--------|
| Exact | SHA-256 fingerprint match | `duplicate_confirmed`, score `1.000` |
| Probable | same amount/currency/direction + date within ±3 days + text similarity ≥ 0.80 | `possible_duplicate` |
| None | everything else | `unique` |

Text similarity combines SequenceMatcher (70 %) and Jaccard token overlap (30 %).

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL
- Redis
- OpenAI API key

### Local Development

```bash
# 1. Clone and set up a virtualenv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# edit .env — set DATABASE_URL and OPENAI_API_KEY at minimum

# 3. Apply migrations and seed categories
alembic upgrade head
python -m app.core.seed_categories

# 4. Start the API
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `/docs`.

### Lint

```bash
ruff check .
ruff format .
```

### Docker (CI parity check)

```bash
docker build -t capable-u-api-dev .
docker build -f Dockerfile.prod -t capable-u-api-prod .
```

## Configuration

All settings are loaded via Pydantic Settings from environment variables (or `.env`). See `.env.example` for the full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection string (required) |
| `OPENAI_API_KEY` | — | OpenAI API key (required) |
| `OPENAI_MODEL` | `gpt-5.4-mini` | Model used for transaction parsing |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `BASE_CURRENCY` | `EUR` | Currency used for base-amount normalization |
| `UPLOAD_DIR` | `./data/uploads` | Directory for uploaded PDFs |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/imports` | Upload a PDF bank statement |
| `GET` | `/imports` | List import jobs (paginated) |
| `GET` | `/imports/{id}/stream` | SSE stream of job status |
| `DELETE` | `/imports/{id}` | Delete job and its transactions |
| `GET` | `/transactions` | List transactions (filters, pagination) |
| `GET` | `/transactions/{id}` | Transaction detail |
| `PATCH` | `/transactions/{id}` | Update transaction (rebuilds fingerprint & duplicates) |
| `DELETE` | `/transactions/{id}` | Delete transaction |
| `POST` | `/transactions/{id}/mark-unique` | Resolve duplicate review |
| `GET` | `/transactions/monthly-summary` | Monthly income/expense by currency & category |
| `GET` | `/transactions/monthly-summary/meta` | Available months and currencies |
| `GET` | `/categories` | List categories |
| `POST` | `/categories` | Create category |
| `PATCH` | `/categories/{id}` | Update category |
| `DELETE` | `/categories/{id}` | Delete category |
| `POST` | `/exchange-rates/update` | Manually refresh exchange rates |
| `POST` | `/generate` | Generate synthetic test transactions |
| `DELETE` | `/generate` | Remove all synthetic test data |

## Database Migrations

```bash
# Create a new migration (after editing a model)
alembic revision --autogenerate -m "describe change"

# Apply all pending migrations
alembic upgrade head
```

**Never edit applied migrations.** Always add a new revision. Keep `downgrade` paths valid.

## Production Deployment

```bash
# Start all services
docker compose -f docker-compose.prod.yml up -d
```

Services started: `db`, `redis`, `api`, `worker`, `beat`.

Exchange rates are refreshed automatically every day at **06:00 UTC** via Celery Beat.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Commits must follow [Conventional Commits](https://www.conventionalcommits.org/) — format enforced by commitlint + Husky. PR titles must match the same format.

Releases are automated via [Release Please](https://github.com/googleapis/release-please).
