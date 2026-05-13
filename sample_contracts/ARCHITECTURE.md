# Architecture

## High-Level Overview

```
Browser
  └── Vite/React SPA (port 5173)
        └── Nginx reverse proxy (port 80)
              ├── /      → frontend static files
              └── /api   → FastAPI backend (port 8000)
                            ├── SQLite (local) / Postgres (Docker)
                            └── ChromaDB (vector store on disk)
```

---

## Backend (`backend/app/`)

### Entry Point — `main.py`

FastAPI app with two route groups:

- **Root routes** (`/`, `/health`) — unauthenticated health probes
- **`/v1/` router** — all real API endpoints, optional `X-API-Key` auth, per-IP rate limiting via `slowapi`

On startup, it seeds `standard_terms_playbook.md` into the DB and Chroma.

---

### The Analysis Lifecycle

#### Step 1 — `POST /v1/analyze`

- Immediately sanitizes input through `guards.py`
- Creates an `Analysis` DB record with `status="queued"`
- Returns `{analysis_id, status}` right away (async, non-blocking)
- Kicks off `_process_analysis()` as a FastAPI `BackgroundTask`

#### Step 2 — `_process_analysis()` → `pipeline.py`

This is the core pipeline, executed in sequence:

```
contract_text
  ↓
[guards.py] filter_malicious_segments()
  — regex-strips prompt injection attempts ("ignore previous instructions", etc.)
  ↓
[pipeline.py] _extract_clauses()
  — 15 regex patterns match clause types: payment_terms, retainage, notice_period,
    indemnification, termination_notice, dispute_resolution, liquidated_damages,
    force_majeure, warranty, insurance, change_order, substantial_completion,
    delay_damages, governing_law, limitation_of_liability
  — contracts >30,000 chars are split into overlapping sections first
  — each match captures ±300 chars of surrounding context as source_text
  ↓
[rag.py] PlaybookRAG.query()
  — for each clause, queries ChromaDB with the source_text
  — retrieves top-3 matching playbook chunks (semantic similarity)
  — returns empty list → clause is skipped (no retrieval = no finding)
  ↓
[pipeline.py] _compare_with_playbook()
  — heuristic scoring: compares extracted numeric values against playbook ranges
  — produces: playbook_standard, deviation, risk_level (low/medium/high/critical)
  ↓
[llm.py] AnthropicClient.complete()  ← ONLY for analysis_type="risks"
  — sends clause + heuristic context to Claude (claude-sonnet-4-6)
  — gets 2-3 sentence human-readable risk explanation + negotiation advice
  — falls back to a deterministic heuristic string if ANTHROPIC_API_KEY is absent
  ↓
[pipeline.py] _merge_findings()
  — deduplicates by clause_type, keeps highest-risk version
  — merges citation chunk IDs from duplicates
  ↓
[guards.py] ensure_retrieval_guardrails()
  — drops any finding that lacks source_text or retrieved_chunks
  ↓
AnalysisResult → stored as JSON in Analysis.result_json → published to event_bus
```

#### Step 3 — `GET /v1/analysis/{id}/stream`

SSE stream powered by `events.py:EventBus` — a simple in-process pub/sub backed by `asyncio.Queue`. The pipeline publishes four event types:

| Event | When |
|---|---|
| `status` | Pipeline phase transitions (extracting, running, etc.) |
| `partial_finding` | Each clause result as it completes (real-time) |
| `final` | Full `AnalysisResult` when pipeline finishes |
| `error` | Unhandled exception |

The frontend opens an `EventSource` immediately after receiving `analysis_id` and renders findings progressively as `partial_finding` events arrive.

---

### Storage

**`database.py`** — SQLAlchemy async sessions

- Local: SQLite at `./data/app.db`
- Docker/prod: Postgres (`asyncpg`)
- Tests: `BYPASS_DB_FOR_TESTS=true` → in-memory, no DB required

**DB Tables (3):**

| Table | Purpose |
|---|---|
| `analyses` | One row per analysis job — stores contract text, status, result JSON, guardrail warnings, usage stats |
| `playbook_versions` | Immutable versioned snapshots of the playbook markdown |
| `playbook_chunks` | Chunked text of each playbook version (800-word chunks), with optional raw embedding bytes |

**ChromaDB (`rag.py`)** — vector store on disk at `./data/chroma`

- One Chroma collection per playbook version: `playbook_{version_id}`
- Uses `DefaultEmbeddingFunction` (local sentence-transformers, no external API)
- Queried per clause with `k=3` nearest neighbors

---

### Playbook System (`playbook.py`)

- Seeded at startup from `standard_terms_playbook.md`
- `PUT /v1/playbook` creates a **new immutable version** (never mutates existing ones)
- Each update triggers `persist_chunks()` → splits content → upserts into Chroma
- `POST /v1/playbook/reindex` rebuilds Chroma embeddings for a specific version

---

### Three Analysis Modes

| Mode | What it does | Uses AI? |
|---|---|---|
| `summary` | Heuristic only — returns `"{ClauseLabel}: {extracted_value}"` | No |
| `obligations` | Heuristic only — returns an action statement for compliance | No |
| `risks` | Calls Claude — gets 2-3 sentence risk + negotiation advice per clause | Yes |

---

### Security Layer (`guards.py`)

- **Input sanitization**: 5 regex patterns catch prompt injection before any processing
- **Output guardrails**: drops findings that lack `source_text` or `retrieved_chunks` — prevents hallucinated findings from leaking through
- All warnings are collected into `guardrail_warnings` on the result

---

## Frontend (`frontend/src/`)

Vite + React + TypeScript, no component library — plain CSS.

**`App.tsx`** — two tabs:

1. **Analyzer tab**: textarea → `POST /v1/analyze` → open `EventSource` on stream URL → render findings progressively via `partial_finding` events
2. **Playbook tab**: `PlaybookManager.tsx` — CRUD for playbook versions

**`FindingsList.tsx`** — renders per-clause results with risk badges

**`api.ts`** — axios instance + `streamUrl()` helper for SSE

---

## Docker Stack

```
nginx (80/443)
├── /     → frontend container (Nginx serving Vite build)
└── /api  → backend container (Uvicorn/FastAPI :8000)
               └── db (Postgres :5432, waits for healthcheck)

Volumes:
  pgdata     → Postgres data
  chromadata → ChromaDB embeddings (persisted across restarts)
```

---

## Key Design Decisions

1. **Async-first**: FastAPI + asyncio throughout; DB sessions use `asyncpg`, analysis runs in background tasks
2. **No LLM for non-risk modes**: `summary` and `obligations` use pure heuristics — faster, cheaper, fully offline
3. **Guardrail-as-filter**: findings without retrieval evidence are silently dropped rather than passed through — prevents grounded-looking hallucinations
4. **Two-phase SSE**: client gets streaming partial results during analysis, not just a final poll — better UX for slow contracts
5. **In-memory mode**: `BYPASS_DB_FOR_TESTS=true` bypasses all DB/Chroma I/O entirely — tests run fully offline with no setup
