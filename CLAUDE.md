# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Contract Clause Analyzer: FastAPI backend + Vite/React frontend that extracts clauses from construction contracts, compares them against a standard terms playbook via a switchable RAG backend (Chroma default, pgvector optional), and streams structured SSE results with risk scoring. All three analysis types (`risks`, `summary`, `obligations`) call Claude via Anthropic tool_use for guaranteed structured output; heuristic fallback is used when no API key is present (tests).

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
| `ANTHROPIC_API_KEY` | — | Required for all 3 analysis types; tests use offline heuristic fallback |
| `ANTHROPIC_MODEL` | `claude-3-opus-20240229` | Override to use a different Claude model (default is outdated) |
| `JWT_SECRET_KEY` | random hex (auto-generated) | Signs JWT tokens; set explicitly in production for persistence across restarts |
| `JWT_EXPIRE_MINUTES` | `1440` | Token lifetime (default 24 h) |
| `DATABASE_URL` | SQLite locally, Postgres in Docker | Auto-detected via `/.dockerenv` |
| `VECTOR_BACKEND` | `chroma` | `chroma` or `pgvector`; pgvector requires Postgres `DATABASE_URL` and `alembic upgrade head` |
| `CHROMA_DIR` | `./data/chroma` | Persistent embedding store (used only when `VECTOR_BACKEND=chroma`) |
| `PLAYBOOK_SEED_PATH` | `./standard_terms_playbook.md` | Seeded into DB + vector store on startup |
| `BYPASS_DB_FOR_TESTS` | `false` | Set `true` for in-memory mode (no DB/Chroma needed) |
| `INLINE_ANALYSIS` | `false` | Run pipeline synchronously instead of as a background task |
| `RATE_LIMIT_PER_MINUTE` | `60` | Per-IP rate limit on analyze/playbook endpoints |
| `RATE_LIMIT_STREAM_PER_MINUTE` | `60` | Per-IP rate limit on SSE stream endpoint |

## Architecture

### API Routes

All routes are prefixed `/v1/` except health probes at root:

- `GET /` and `GET /health` — health probes (no auth required)
- `POST /v1/auth/register` — create account `{email, password}` → `{id, email, created_at}`
- `POST /v1/auth/login` — `{email, password}` → `{access_token, token_type}`
- `POST /v1/analyze` → returns `{analysis_id, status}` immediately; requires `Authorization: Bearer <token>`
- `POST /v1/analyze/upload` → multipart form upload (`file`, `analysis_type`, `playbook_version_id?`); accepts PDF, DOCX, TXT up to 20 MB; extracts text then runs the same pipeline as `/v1/analyze`
- `GET /v1/analysis/{id}` → poll for result (`AnalysisResult`) or status (`AnalysisStatusResponse`)
- `GET /v1/analysis/{id}/stream` → SSE stream; events: `status`, `partial_finding`, `final`, `error`; accepts `?token=` for EventSource (can't send headers)
- `GET /v1/playbook`, `PUT /v1/playbook` — read/update current playbook
- `GET /v1/playbook/versions`, `GET /v1/playbook/versions/{id}` — version history
- `POST /v1/playbook/reindex` — rebuild vector store embeddings for a playbook version

**Typical client flow:** POST `/v1/analyze` (or `/v1/analyze/upload` for files) → open `EventSource` on `/v1/analysis/{id}/stream` → receive `status` events per section scanned, then `partial_finding` events as each clause completes → `final` event with complete result.

### Backend (`backend/app/`)

The analysis flow is a deterministic pipeline in `pipeline.py`:

1. **`guards.py`** — sanitize input, detect prompt injection, emit `GuardrailWarning`s
2. **`pipeline.py:_extract_clauses_from_section`** — regex-based extraction using 21 clause patterns across overlapping sections; a `status` SSE event is emitted after each section so clients see scanning progress. Contracts >30 000 chars are split into overlapping sections first. Patterns: `payment_terms`, `retainage`, `notice_period`, `indemnification`, `termination_notice`, `dispute_resolution`, `liquidated_damages`, `force_majeure`, `warranty`, `insurance`, `change_order`, `substantial_completion`, `delay_damages`, `governing_law`, `limitation_of_liability`, `non_compete`, `ip_assignment`, `data_privacy`, `exclusivity`, `cure_period`, `assignment_rights`.
3. **`rag.py` / `rag_pgvector.py`** — pluggable RAG layer. `BaseRAG` (`rag_base.py`) defines the async interface (`collection_count`, `reset_version`, `query`, `bm25_query`, `hybrid_query`). `ChromaRAG` wraps fastembed + ChromaDB; `PgvectorRAG` uses asyncpg + pgvector with the same BGE-small-en embedding model. `get_rag_backend()` factory reads `VECTOR_BACKEND` and returns the right singleton; `pgvector` silently falls back to `chroma` if `DATABASE_URL` is SQLite. `PlaybookRAG()` is an alias for the factory.
4. **`pipeline.py:_compare_with_playbook` (Pass 1)** — heuristic deviation scoring for **all** extracted clauses; results sorted by risk descending; top 30 (`_MAX_LLM_FINDINGS`) go to the LLM, remainder get heuristic-only `Finding` objects at `confidence=0.3`
5. **`pipeline.py:_call_llm_for_clause` (Pass 2)** — concurrent LLM enrichment for the top-30 batch via `asyncio.as_completed` + `Semaphore(5)`; each call is wrapped in `asyncio.wait_for(timeout=45s)` — timeout falls back to heuristic finding rather than failing; heuristic fallback used when no API key is set
6. **`pipeline.py:_merge_findings`** — deduplicates findings by clause type, keeps highest-risk version
7. **`guards.py:ensure_retrieval_guardrails`** — drops findings missing `source_text` or `retrieved_chunks`

**Large-contract safeguards:** `_PIPELINE_TIMEOUT_SECS = 600` global timeout in `_process_analysis` (wraps the entire pipeline in `asyncio.wait_for`); emits an `error` SSE event and marks the analysis `failed` on expiry.

**Playbook versioning:** `playbook.py` manages `PlaybookVersion` and `PlaybookChunk` DB records. On startup, `main.py:startup_event` seeds `standard_terms_playbook.md` → DB → vector store. `PUT /v1/playbook` creates immutable new versions.

**Storage modes:**
- Default (local): SQLite at `./data/app.db` (create `./data/` if missing)
- Docker/prod: Postgres (`postgres+asyncpg://analyzer:analyzer@db:5432/analyzer`)
- Tests: `BYPASS_DB_FOR_TESTS=true` enables in-memory mode; the test file sets this automatically

**SSE streaming:** `events.py:event_bus` is a pub/sub used to relay pipeline progress to `GET /v1/analysis/{id}/stream`.

**Schema migrations:** managed by Alembic in `migrations/`. `migrations/env.py` reads `DATABASE_URL` at runtime; `alembic.ini` leaves `sqlalchemy.url` blank intentionally.

### Frontend (`frontend/src/`)

Vite + React + TypeScript. Uses `axios` for API calls and native `EventSource` for SSE. No UI component library — dark glassmorphism design in `styles.css`. Key components: `AuthPage.tsx` (login/register gate), `FindingsList.tsx` (renders risk findings), `PlaybookManager.tsx` (playbook CRUD). JWT token stored in `localStorage`; axios interceptor attaches `Authorization: Bearer` on every request. Tests use Vitest + `@testing-library/react`.

File upload: `App.tsx` includes a drag-and-drop zone + Browse button (accepts `.pdf`, `.docx`, `.txt`). When a file is selected it calls `analyzeUpload()` in `api.ts` which POSTs multipart to `/v1/analyze/upload`; otherwise the textarea path posts JSON to `/v1/analyze`.

### Deployment

`docker-compose.yml` runs four services: `db` (Postgres), `backend` (FastAPI on 8000), `frontend` (Vite build served by Nginx), `nginx` (reverse proxy: `/` → frontend, `/api` → backend on 80/443).
