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

FastAPI app with three route groups:

- **Root routes** (`/`, `/health`) — unauthenticated health probes
- **`/v1/auth/` router** — `POST /register` and `POST /login`; returns JWT Bearer tokens (no auth required)
- **`/v1/` router** — all real API endpoints; JWT Bearer auth via `Authorization` header (or `?token=` for SSE EventSource); per-IP rate limiting via `slowapi`

Auth is stateless — `get_current_user_id()` decodes the JWT without a DB lookup. In-memory/test mode returns `None` so tests run without tokens.

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
[rag.py] PlaybookRAG.hybrid_query()
  — for each clause, runs semantic search (ChromaDB) + BM25 keyword search in parallel
  — semantic results take priority; BM25 fills remaining slots up to k=3
  — union is deduplicated by chunk_id
  — returns empty list → clause is skipped (no retrieval = no finding)
  ↓
[pipeline.py] _compare_with_playbook()
  — heuristic scoring: compares extracted numeric values against playbook ranges
  — produces: playbook_standard, deviation, risk_level (low/medium/high/critical)
  ↓
[llm.py] AnthropicClient  ← called for ALL three analysis types via Anthropic tool_use
  — risks    → analyze_risk()     → LLMFindingOutput  (risk_level, deviation_summary, recommendation, confidence)
  — summary  → summarize_clause() → LLMSummaryOutput  (plain_language, key_terms, risk_flag)
  — obligations → extract_obligations() → LLMObligationOutput (obligations[], party, deadline, consequence)
  — tool_choice={"type":"tool"} forces Claude to always emit structured JSON, never free text
  — prompt includes retrieved playbook chunks injected with cache_control ephemeral for prompt caching
  — falls back to empty typed schema objects if ANTHROPIC_API_KEY is absent (tests run offline)
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

**DB Tables (4):**

| Table | Purpose |
|---|---|
| `users` | One row per registered user — email, bcrypt-hashed password, is_active, created_at |
| `analyses` | One row per analysis job — contract text, status, result JSON, guardrail warnings, usage stats, `user_id` FK |
| `playbook_versions` | Immutable versioned snapshots of the playbook markdown |
| `playbook_chunks` | Chunked text of each playbook version (sentence-aware 800-char chunks with heading context) |

**ChromaDB (`rag.py`)** — vector store on disk at `./data/chroma`

- One Chroma collection per playbook version + embed tag: `playbook_{version_id}_bge_small_v1`
- Embed tag (`_EMBED_TAG`) is bumped whenever the model changes, automatically routing to a fresh empty collection and triggering re-embedding on next startup
- Embedding model: `BAAI/bge-small-en-v1.5` (384-dim, ~130 MB) via `fastembed`, wrapped in a custom `_FastEmbedFn(EmbeddingFunction)` — no external API, runs locally
- Chunks include their nearest markdown section heading for richer embedding context
- Queried per clause with `k=3` nearest neighbors; L2 distance threshold 1.2 filters unrelated chunks
- BM25 index built on-the-fly over the same chunk set for keyword recall

---

### Playbook System (`playbook.py`)

- Seeded at startup from `standard_terms_playbook.md`
- `PUT /v1/playbook` creates a **new immutable version** (never mutates existing ones)
- Each update triggers `persist_chunks()` → splits content → upserts into Chroma
- `POST /v1/playbook/reindex` rebuilds Chroma embeddings for a specific version

---

### Three Analysis Modes

All three modes call Claude via `tool_use` for structured output. The difference is which tool schema is invoked and what the prompt emphasises.

| Mode | Tool / Schema | Output fields |
|---|---|---|
| `risks` | `record_risk_finding` → `LLMFindingOutput` | risk_level, deviation_summary, recommendation, confidence |
| `summary` | `record_clause_summary` → `LLMSummaryOutput` | plain_language, key_terms, risk_flag |
| `obligations` | `record_obligations` → `LLMObligationOutput` | obligations[], party, deadline, consequence |

---

### Auth Layer (`auth.py`)

- **JWT Bearer tokens** — `POST /v1/auth/register` → `POST /v1/auth/login` → `access_token`
- Tokens verified stateless via `pyjwt`; no DB lookup per request
- Passwords hashed with `bcrypt` (cost factor from `bcrypt.gensalt()`)
- SSE stream accepts `?token=` query param because `EventSource` cannot set `Authorization` headers
- In-memory/test mode bypasses auth entirely (`get_current_user_id` returns `None`)

### Security Layer (`guards.py`)

- **Input sanitization**: 5 regex patterns catch prompt injection before any processing
- **Output guardrails**: drops findings that lack `source_text` or `retrieved_chunks` — prevents hallucinated findings from leaking through
- All warnings are collected into `guardrail_warnings` on the result

---

## Frontend (`frontend/src/`)

Vite + React + TypeScript. No component library — dark glassmorphism design in `styles.css` (deep navy background, frosted-glass cards, purple accent).

**`AuthPage.tsx`** — login/register gate rendered before the main app if no JWT token is in `localStorage`. Calls `/v1/auth/register` then `/v1/auth/login` on sign-up; stores `access_token` via `setToken()`.

**`api.ts`** — axios instance with a request interceptor that attaches `Authorization: Bearer <token>`. `streamUrl()` appends `?token=` for EventSource. Token helpers: `getToken()`, `setToken()`, `clearToken()`.

**`App.tsx`** — checks `getToken()` on mount; renders `AuthPage` if absent, otherwise the main app. Contains a sign-out button that calls `clearToken()`. Two tabs:

1. **Analyzer tab**: textarea → `POST /v1/analyze` → open `EventSource` on stream URL → render findings progressively via `partial_finding` events
2. **Playbook tab**: `PlaybookManager.tsx` — CRUD for playbook versions

**`FindingsList.tsx`** — renders per-clause results with risk badges, confidence %, and retrieved evidence chunks

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

1. **Async-first**: FastAPI + asyncio throughout; DB sessions use `asyncpg`/`aiosqlite`, analysis runs in background tasks
2. **tool_use for all three modes**: forces Claude to emit typed JSON (never free text), eliminating fragile regex parsing of LLM responses; each mode has its own tool schema
3. **Hybrid RAG (semantic + BM25)**: ChromaDB semantic search handles paraphrase matching; BM25 fills recall gaps for exact legal terms; union is deduplicated with semantic results prioritised
4. **Embed-tag versioned Chroma collections**: bumping `_EMBED_TAG` in `rag.py` routes to a fresh collection automatically, so a model upgrade triggers clean re-embedding without manual intervention
5. **Stateless JWT auth**: no per-request DB lookup; tokens are self-contained and verified with `pyjwt`; in-memory/test mode bypasses auth entirely so tests need no token setup
6. **Guardrail-as-filter**: findings without retrieval evidence are silently dropped — prevents grounded-looking hallucinations from leaking through
7. **Two-phase SSE**: client streams partial results during analysis rather than polling for a final result — better UX for long contracts
8. **In-memory mode**: `BYPASS_DB_FOR_TESTS=true` bypasses all DB/Chroma I/O — tests run fully offline with no setup
