# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Contract Clause Analyzer: FastAPI backend + Vite/React frontend that extracts clauses from construction contracts, compares them against a standard terms playbook via Chroma RAG, and streams structured SSE results with risk scoring. Uses the Anthropic SDK (Claude) for the `risks` analysis type; `summary` and `obligations` use heuristic-only pipelines.

## Commands

### Backend

```bash
# Setup (from repo root, Python 3.11+ required)
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# Apply DB schema (required before first run and after schema changes)
alembic upgrade head

# Run dev server
uvicorn backend.app.main:app --reload --port 8000

# Run all tests (test file sets its own env vars; no manual config needed)
pytest backend/tests

# Run a single test file
pytest backend/tests/test_api.py -vv

# Run a single test by name
pytest backend/tests/test_api.py::test_health -vv
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host --port 5173

# Run tests
npm test

# Build
npm run build
```

### Docker (full stack)

```bash
docker compose build
docker compose up -d
docker compose logs -f backend frontend nginx
```

## Environment Variables

Copy from `.env.example`. Key vars:

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for `risks` analysis type; tests use offline fallback |
| `ANTHROPIC_MODEL` | `claude-3-opus-20240229` | Override to use a different Claude model (default is outdated) |
| `API_KEY` | — | When set, all routes require `X-API-Key` header; SSE stream also accepts `?api_key=` |
| `DATABASE_URL` | SQLite locally, Postgres in Docker | Auto-detected via `/.dockerenv` |
| `CHROMA_DIR` | `./data/chroma` | Persistent embedding store |
| `PLAYBOOK_SEED_PATH` | `./standard_terms_playbook.md` | Seeded into DB + Chroma on startup |
| `BYPASS_DB_FOR_TESTS` | `false` | Set `true` for in-memory mode (no DB/Chroma needed) |
| `INLINE_ANALYSIS` | `false` | Run pipeline synchronously instead of as a background task |
| `RATE_LIMIT_PER_MINUTE` | `60` | Per-IP rate limit on analyze/playbook endpoints |
| `RATE_LIMIT_STREAM_PER_MINUTE` | `60` | Per-IP rate limit on SSE stream endpoint |

## Architecture

### API Routes

All routes are prefixed `/v1/` except health probes at root:

- `GET /` and `GET /health` — health probes (no auth required)
- `POST /v1/analyze` → returns `{analysis_id, status}` immediately; pipeline runs as a background task
- `GET /v1/analysis/{id}` → poll for result (`AnalysisResult`) or status (`AnalysisStatusResponse`)
- `GET /v1/analysis/{id}/stream` → SSE stream; events: `status`, `partial_finding`, `final`, `error`
- `GET /v1/playbook`, `PUT /v1/playbook` — read/update current playbook
- `GET /v1/playbook/versions`, `GET /v1/playbook/versions/{id}` — version history
- `POST /v1/playbook/reindex` — rebuild Chroma embeddings for a playbook version

**Typical client flow:** POST `/v1/analyze` → open `EventSource` on `/v1/analysis/{id}/stream` → receive `partial_finding` events as clauses are processed → `final` event with complete result.

### Backend (`backend/app/`)

The analysis flow is a deterministic pipeline in `pipeline.py`:

1. **`guards.py`** — sanitize input, detect prompt injection, emit `GuardrailWarning`s
2. **`pipeline.py:_extract_clauses`** — regex-based extraction using 15 clause patterns: `payment_terms`, `retainage`, `notice_period`, `indemnification`, `termination_notice`, `dispute_resolution`, `liquidated_damages`, `force_majeure`, `warranty`, `insurance`, `change_order`, `substantial_completion`, `delay_damages`, `governing_law`, `limitation_of_liability`. Contracts >30 000 chars are split into overlapping sections first.
3. **`rag.py:PlaybookRAG`** — in-memory Chroma-backed retrieval; queries playbook chunks per extracted clause
4. **`pipeline.py:_compare_with_playbook`** — heuristic deviation scoring against retrieved chunk text → `risk_level` (low/medium/high/critical)
5. **`llm.py:AnthropicClient`** — called only for `analysis_type=risks`; heuristic fallback used in tests
6. **`pipeline.py:_merge_findings`** — deduplicates findings by clause type, keeps highest-risk version
7. **`guards.py:ensure_retrieval_guardrails`** — drops findings missing `source_text` or `retrieved_chunks`

**Playbook versioning:** `playbook.py` manages `PlaybookVersion` and `PlaybookChunk` DB records. On startup, `main.py:startup_event` seeds `standard_terms_playbook.md` → DB → Chroma. `PUT /v1/playbook` creates immutable new versions.

**Storage modes:**
- Default (local): SQLite at `./data/app.db` (create `./data/` if missing)
- Docker/prod: Postgres (`postgres+asyncpg://analyzer:analyzer@db:5432/analyzer`)
- Tests: `BYPASS_DB_FOR_TESTS=true` enables in-memory mode; the test file sets this automatically

**SSE streaming:** `events.py:event_bus` is a pub/sub used to relay pipeline progress to `GET /v1/analysis/{id}/stream`.

**Schema migrations:** managed by Alembic in `migrations/`. `migrations/env.py` reads `DATABASE_URL` at runtime; `alembic.ini` leaves `sqlalchemy.url` blank intentionally.

### Frontend (`frontend/src/`)

Vite + React + TypeScript. Uses `axios` for API calls and native `EventSource` for SSE. No UI component library — plain CSS in `styles.css`. Key components: `FindingsList.tsx` (renders risk findings), `PlaybookManager.tsx` (playbook CRUD). Tests use Vitest + `@testing-library/react`.

### Deployment

`docker-compose.yml` runs four services: `db` (Postgres), `backend` (FastAPI on 8000), `frontend` (Vite build served by Nginx), `nginx` (reverse proxy: `/` → frontend, `/api` → backend on 80/443).
