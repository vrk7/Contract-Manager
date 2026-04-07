# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Contract Clause Analyzer: FastAPI backend + Vite/React frontend that extracts clauses from construction contracts, compares them against a standard terms playbook via Chroma RAG, and streams structured SSE results with risk scoring. Uses the Anthropic SDK (Claude) for the `risks` analysis type; the `summary` and `obligations` types use heuristic-only pipelines.

## Commands

### Backend

```bash
# Setup (from repo root, Python 3.11+ required)
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# Run dev server
uvicorn backend.app.main:app --reload --port 8000

# Run all tests
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
| `ANTHROPIC_MODEL` | `claude-3-opus-20240229` | Override to use a different Claude model |
| `DATABASE_URL` | SQLite locally, Postgres in Docker | Auto-detected via `/.dockerenv` |
| `CHROMA_DIR` | `./data/chroma` | Persistent embedding store |
| `PLAYBOOK_SEED_PATH` | `./standard_terms_playbook.md` | Seeded into DB + Chroma on startup |
| `BYPASS_DB_FOR_TESTS` | `false` | Set `true` to use in-memory mode (no DB/Chroma needed) |
| `INLINE_ANALYSIS` | `false` | Run pipeline synchronously instead of as a background task |

## Architecture

### Backend (`backend/app/`)

The analysis flow is a deterministic pipeline in `pipeline.py`:

1. **`guards.py`** — sanitize input, detect prompt injection, emit `GuardrailWarning`s
2. **`pipeline.py:_extract_clauses`** — regex-based clause extraction (payment terms, retainage, notice periods, indemnification, termination, dispute resolution, liquidated damages)
3. **`rag.py:PlaybookRAG`** — in-memory Chroma-backed retrieval; queries playbook chunks per extracted clause
4. **`pipeline.py:_compare_with_playbook`** — heuristic deviation scoring against retrieved chunk text → `risk_level` (low/medium/high/critical)
5. **`llm.py:AnthropicClient`** — called only for `analysis_type=risks`; heuristic fallback used in tests
6. **`pipeline.py:_merge_findings`** — deduplicates findings by clause type, keeps highest-risk version
7. **`guards.py:ensure_retrieval_guardrails`** — drops findings missing `source_text` or `retrieved_chunks`

**Playbook versioning:** `playbook.py` manages `PlaybookVersion` and `PlaybookChunk` DB records. On startup, `main.py:startup_event` seeds `standard_terms_playbook.md` → DB → Chroma. Updates via `PUT /playbook` create immutable new versions.

**Storage modes:**
- Default (local): SQLite at `./data/app.db`
- Docker/prod: Postgres (`postgres+asyncpg://analyzer:analyzer@db:5432/analyzer`)
- Tests: `BYPASS_DB_FOR_TESTS=true` enables in-memory mode bypassing all DB/Chroma calls

**SSE streaming:** `events.py:event_bus` is a pub/sub used to relay pipeline progress to `GET /analysis/{id}/stream`. Events: `status`, `partial_finding`, `final`, `error`.

### Frontend (`frontend/src/`)

Vite + React + TypeScript. Uses `axios` for API calls and native `EventSource` for SSE streaming. No UI component library — plain CSS in `styles.css`. Tests use Vitest + `@testing-library/react`.

### Deployment

`docker-compose.yml` runs four services: `db` (Postgres), `backend` (FastAPI on 8000), `frontend` (Vite build served by Nginx), `nginx` (reverse proxy: `/` → frontend, `/api` → backend on 80/443).
