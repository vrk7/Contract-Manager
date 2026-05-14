# Contract Manager — Full Improvement Roadmap

All 160 items from the improvement analysis, ordered by dependency layer.
Items within each phase can be worked in parallel unless noted otherwise.
Each item includes its original number, estimated effort, and hard dependencies.

---

## Legend

| Symbol | Meaning |
|---|---|
| `[deps: #n, #m]` | Must complete items n and m first |
| `⚡ Quick` | Under 2 hours |
| `🕐 Half day` | 2–4 hours |
| `📅 1 day` | Full working day |
| `📆 2–3 days` | Multi-day task |
| `🗓️ 1 week+` | Large effort |
| ✅ | Done |
| 🔶 | Partially done |

---

## Phase 0 — Zero-Dependency Quick Wins
> Do on Day 1. No prerequisites. Each item is a self-contained change.

### AI Layer
| # | Item | Effort | Status |
|---|---|---|---|
| 1 | Update default model to `claude-sonnet-4-20250514` in `config.py` | ⚡ Quick | ✅ |
| 2 | Add Anthropic prompt caching (`cache_control`) on playbook content block in `llm.py` | 🕐 Half day | ✅ |
| 3 | Switch LLM response to structured output (`response_format` / JSON mode) in `llm.py` + `pipeline.py` | 📅 1 day | |
| 4 | Add chain-of-thought prompting for risk assessments — update system prompt in `llm.py` | ⚡ Quick | ✅ |
| 5 | Extend Claude calls to `summary` and `obligations` analysis types — currently heuristic-only in `pipeline.py` | 📅 1 day | |
| 12 | Integrate LLM observability — Helicone or LangSmith as drop-in wrapper around `AsyncAnthropic` client | 🕐 Half day | |

### Observability (do now — helps debug everything that follows)
| # | Item | Effort | Status |
|---|---|---|---|
| 111 | Replace all `print()` with `structlog` JSON logger; attach `analysis_id`, `request_id`, `user_ip` on every log line | 🕐 Half day | ✅ |

### Security (low-risk, high-value hardening)
| # | Item | Effort | Status |
|---|---|---|---|
| 101 | Add `USER appuser` directive to both backend and frontend Dockerfiles — run as non-root | ⚡ Quick | ✅ |
| 102 | Pin base image versions: `python:3.11.9-slim`, `node:20.14-alpine` (not floating tags) | ⚡ Quick | ✅ |

---

## Phase 1 — Development Foundation
> Week 1. Establishes the safety net for all future work. Nothing should be merged without these.

### CI/CD Pipeline
| # | Item | Effort | Notes | Status |
|---|---|---|---|---|
| 135 | GitHub Actions: `push → ruff lint → mypy → eslint → pytest → vitest → docker build → smoke test` | 📅 1 day | Enables all future quality gates | ✅ |
| 139 | Dependabot or Renovate — automated dependency update PRs for pip and npm | ⚡ Quick | | ✅ |
| 140 | Conventional commits + `semantic-release` for automated changelog and version bumping | 🕐 Half day | | ✅ |
| 106 | `pip-audit` and `npm audit` steps in CI pipeline | ⚡ Quick | [deps: #135] | 🔶 pip-audit done; npm audit pending |
| 107 | Bandit (Python SAST) and Semgrep in CI | ⚡ Quick | [deps: #135] | 🔶 Bandit done; Semgrep pending |

### Testing Baseline
| # | Item | Effort | Notes | Status |
|---|---|---|---|---|
| 121 | Unit tests for `rag.py`, `playbook.py`, `database.py`, `guards.py` — currently zero coverage | 📆 2–3 days | | 🔶 `guards.py` done; others pending |
| 122 | Unit tests for all 15 clause extraction patterns including edge cases (multi-value, abbreviated units) | 📅 1 day | | |
| 132 | Coverage gate in CI — block merges below 80% backend / 60% frontend | ⚡ Quick | [deps: #135, #121] | |

---

## Phase 2 — Database & Schema Hardening
> Week 1–2. Must happen before auth, user-specific features, confidence scores, and multi-tenancy.
> Each item requires an Alembic migration.

| # | Item | Effort | Notes |
|---|---|---|---|
| 52 | Add DB indexes: `(status, created_at)`, `(analysis_type, created_at)` on `analyses`; `(version_id)` on `playbook_chunks` | 🕐 Half day | New migration file |
| 53 | Add soft deletes — `deleted_at TIMESTAMP` on `analyses` and `playbook_versions`; filter in all queries | 📅 1 day | New migration |
| 54 | Add `audit_log` table — `(id, table_name, row_id, action, changed_by, changed_at, diff_json)` | 📅 1 day | New migration |
| 47 | Add `request_id` column on `analyses`; generate UUID per request in middleware; propagate through logs and SSE events | 🕐 Half day | New migration + middleware |

---

## Phase 3 — RAG & Clause Extraction
> Week 2–3. Core intelligence upgrade. Items 10 and 11 (HyDE, multi-query) are explicitly blocked on this phase completing.
> Do RAG improvements before clause extraction — better retrieval makes extraction evaluation meaningful.

### RAG Improvements
| # | Item | Effort | Notes |
|---|---|---|---|
| 23 | Switch `chunk_playbook()` in `playbook.py` from word-based to sentence-aware split with 2–3 sentence overlap | 📅 1 day | |
| 24 | Prepend section heading to each chunk before embedding so structural context is preserved | 🕐 Half day | [deps: #23] |
| 25 | Add BM25 keyword search alongside Chroma semantic search; union and score-merge results | 📆 2–3 days | Add `rank_bm25` dependency |
| 26 | Add cross-encoder reranking before returning top-k (`cross-encoder/ms-marco-MiniLM-L-6-v2`) | 📅 1 day | [deps: #25] |
| 27 | Similarity score threshold — drop chunks below 0.35 cosine similarity instead of always returning k | 🕐 Half day | |
| 28 | Upgrade embedding model from `all-MiniLM-L6-v2` to `legal-bert-base-uncased` or `thenlper/gte-large` | 📅 1 day | Requires Chroma reindex |
| 29 | Parent-child chunking — embed sentence-level chunks, retrieve paragraph-level parents for context | 📆 2–3 days | Schema change to `playbook_chunks` |
| 30 | Cache embeddings by content hash — avoid re-embedding identical chunks on reindex | 🕐 Half day | |
| 31 | Add asyncio lock around Chroma collection access in `rag.py` to prevent race conditions under concurrent requests | ⚡ Quick | |
| 32 | Multi-source RAG — allow user-uploaded supplemental documents (case law, templates) alongside playbook | 📆 2–3 days | [deps: Phase 6 file upload] |

### Clause Extraction
| # | Item | Effort | Notes |
|---|---|---|---|
| 15 | Hybrid extraction: regex pre-filter → spaCy NER for entities → Claude for ambiguous cases | 📆 2–3 days | Add `spacy` dependency |
| 16 | NLP date normalization — convert "thirty (30) days" → `{value: 30, unit: "days"}` as structured field | 📅 1 day | [deps: #15] |
| 17 | Multi-clause detection — "payment within 30 or 45 days depending on milestone" currently breaks regex | 📅 1 day | |
| 18 | Section-aware extraction — record which contract section (e.g. "Article 5.3") each clause was found in | 📅 1 day | Schema change on `findings` |
| 19 | Cross-reference detection — flag when clause A modifies clause B ("notwithstanding Section 12.1") | 📆 2–3 days | |
| 20 | Missing clause detection — if a standard term (force_majeure, limitation_of_liability) is entirely absent, flag it | 📅 1 day | |
| 21 | Overlapping clause detection — two clauses in the same contract that contradict each other | 📆 2–3 days | |
| 22 | Expand clause types beyond 15: non-compete, IP assignment, data privacy, exclusivity, minimum purchase, SLA penalties, cure periods, assignment rights | 📆 2–3 days | |

---

## Phase 4 — Risk Scoring
> Week 3. Depends on Phase 3 chunking being solid (playbook tables must be parseable).

| # | Item | Effort | Notes |
|---|---|---|---|
| 33 | Parse playbook risk tables at startup into `{clause_type: {low: range, medium: range, critical: threshold}}` structured config — remove all hardcoded heuristics from `pipeline.py` | 📅 1 day | Requires playbook format to be consistent |
| 34 | Numeric comparison for scoring — compare extracted values directly against config ranges instead of regex-matching retrieved text | 🕐 Half day | [deps: #33] |
| 35 | Inter-clause risk amplification — long payment terms + high retainage should compound the overall risk score | 📅 1 day | [deps: #34] |
| 36 | Jurisdiction-aware scoring — load jurisdiction rules from config; same clause can be critical in DE, acceptable in US | 📆 2–3 days | [deps: #33] |
| 37 | Industry-specific playbooks — construction vs SaaS vs manufacturing have different norms; tag playbook versions by industry | 📆 2–3 days | Schema change on `playbook_versions` |
| 38 | Risk trend tracking — compare each finding against historical average for that clause type across prior analyses | 📅 1 day | [deps: Phase 2 indexes] |

---

## Phase 5 — API & Auth
> Week 3–4. Blocks all user-specific features (feedback, multi-tenancy, org-scoped rate limits).
> Do auth before building any frontend features that depend on identity.

| # | Item | Effort | Notes |
|---|---|---|---|
| 60 | Make API key required by default in production; optional only when `DEBUG=true` | ⚡ Quick | |
| 61 | JWT auth — issue short-lived access tokens + refresh tokens for web UI users | 📅 1 day | |
| 62 | OAuth2/OIDC integration via Auth0 or Clerk — social login for web UI | 📆 2–3 days | [deps: #61] |
| 63 | Scoped API keys — read-only vs write vs admin; bound to org_id | 📅 1 day | [deps: Phase 2 schema] |
| 64 | Brute force protection — lock API key after N consecutive failures; exponential backoff | 🕐 Half day | |
| 65 | Rate limiting per user/org — replace IP-only limit in `slowapi` with user-aware limits | 📅 1 day | [deps: #61] |
| 66 | OpenAPI schema fully documented — examples, error schemas, deprecation notices on every route | 📅 1 day | |
| 67 | Client SDK generation from OpenAPI spec — Python and TypeScript SDKs auto-generated | 📆 2–3 days | [deps: #66] |
| 68 | API versioning strategy — document when to bump `/v2/`, how to support dual versions | 🕐 Half day | |

---

## Phase 6 — Backend Architecture & Scalability
> Week 4–5. Enables horizontal scaling, file upload, webhooks, and batch analysis.

### Task Queue
| # | Item | Effort | Notes |
|---|---|---|---|
| 39 | Replace `BackgroundTasks` with Celery + Redis — separate worker process, horizontal scaling | 📆 2–3 days | Blocks #13, #87 |
| 40 | Retry logic with exponential backoff on LLM calls, Chroma queries, DB writes | 📅 1 day | [deps: #39] |
| 41 | Circuit breaker pattern via `tenacity` or `pybreaker` for Anthropic API and Chroma | 📅 1 day | [deps: #40] |

### Request Handling
| # | Item | Effort | Notes |
|---|---|---|---|
| 42 | Result caching by `hash(contract_text + playbook_version_id + analysis_type)` — return cached result on re-submission | 📅 1 day | |
| 43 | `GET /v1/analyses` list endpoint with filtering by status, type, date | 📅 1 day | |
| 44 | Cursor-based pagination on list endpoint | 🕐 Half day | [deps: #43] |
| 45 | Webhook support — `POST /v1/webhooks` to register a URL; notify on analysis completion | 📆 2–3 days | [deps: #39, #61] |
| 46 | Idempotency keys on `POST /v1/analyze` — `Idempotency-Key` header prevents duplicate analyses from retries | 🕐 Half day | |
| 48 | Graceful shutdown — drain in-flight analyses before SIGTERM, finish SSE streams cleanly | 📅 1 day | [deps: #39] |
| 49 | Deep health check — `/health` verifies DB connectivity, Chroma availability, and LLM reachability | 🕐 Half day | |
| 50 | Response compression — gzip/brotli middleware on all JSON responses | ⚡ Quick | |
| 51 | ETag support on `GET /v1/analysis/{id}` — avoid re-transferring unchanged results | 🕐 Half day | |

### Database Operations
| # | Item | Effort | Notes |
|---|---|---|---|
| 56 | PgBouncer connection pooling in Docker Compose production stack | 🕐 Half day | |
| 55 | Read replica routing — send GET queries to replica, writes to primary | 📆 2–3 days | Needs infra support |

### File Handling
| # | Item | Effort | Notes |
|---|---|---|---|
| 57 | File upload endpoint — `POST /v1/analyze` accepts `multipart/form-data` with PDF/DOCX | 📅 1 day | |
| 58 | PDF/DOCX text extraction — `pypdf2` + `python-docx` with layout-aware parsing | 📅 1 day | [deps: #57] |
| 59 | Contract text validation middleware — reject empty, binary, >100k tokens, non-UTF-8 | 🕐 Half day | |

---

## Phase 7 — Security Hardening
> Week 5. Can be done in parallel with Phase 6. Must complete before any public deployment.

| # | Item | Effort | Notes |
|---|---|---|---|
| 97 | Strengthen injection detection — add zero-width character detection, token budget limits, `guardrails-ai` library | 📅 1 day | |
| 98 | PII detection and masking — detect names, addresses, bank details in contracts; optionally redact before LLM | 📆 2–3 days | Use `presidio` library |
| 99 | Content Security Policy headers — add via middleware or nginx | ⚡ Quick | |
| 100 | CSRF protection on all state-changing endpoints | 🕐 Half day | [deps: #61] |
| 103 | Secrets management — Docker secrets or HashiCorp Vault; remove plaintext env vars from `docker-compose.yml` | 📅 1 day | |
| 104 | TLS certificate management — Let's Encrypt via Certbot in nginx config | 📅 1 day | |
| 105 | WAF in front of nginx — OWASP ModSecurity ruleset | 📆 2–3 days | |
| 108 | Data retention policy — cron job to auto-delete analyses older than configurable N days | 🕐 Half day | |
| 109 | GDPR compliance — right-to-erasure endpoint, data export endpoint, processing documentation | 📆 2–3 days | [deps: #61, #108] |
| 110 | Per-user rate limiting and CAPTCHA on public endpoints to defeat IP-rotation bypass | 📅 1 day | [deps: #65] |

---

## Phase 8 — Advanced AI Features
> Week 5–6. Explicitly blocked on Phase 3 (RAG), Phase 2 (schema), and Phase 5 (auth).

| # | Item | Effort | Notes |
|---|---|---|---|
| 10 | HyDE retrieval — generate hypothetical playbook answer via LLM, use it to query Chroma | 📅 1 day | [deps: #23–28] |
| 11 | Multi-query retrieval — 3 phrasings per clause query, union results, deduplicate | 📅 1 day | [deps: #23–28] |
| 6 | Self-consistency checks — run critical findings through a second LLM pass to reduce hallucinations | 📅 1 day | [deps: #3, #39] |
| 7 | Confidence scores per finding (0.0–1.0) — new column on findings schema, populated by LLM | 📅 1 day | [deps: #3, Phase 2] |
| 8 | User feedback loop — thumbs up/down on findings stored in DB; used as few-shot examples | 📅 1 day | [deps: #61, Phase 2] |
| 9 | Model comparison mode — run same contract through Sonnet vs Opus, log quality and cost delta | 📆 2–3 days | [deps: #111, #118] |
| 13 | Batch API — `POST /v1/analyze/batch` with Anthropic Batch endpoint (50% cost reduction) | 📆 2–3 days | [deps: #39] |
| 14 | Uncertainty quantification — flag findings where LLM token probabilities are low | 📆 2–3 days | [deps: #3, #7] |

---

## Phase 9 — Full Observability Stack
> Week 6. Items #111 and #12 already done in Phase 0. This phase builds on them.

| # | Item | Effort | Notes |
|---|---|---|---|
| 112 | OpenTelemetry traces — instrument every pipeline step; export to Jaeger or Tempo | 📆 2–3 days | [deps: #111] |
| 113 | Prometheus metrics — request latency p50/p95/p99, queue depth, LLM token rate, error rate | 📅 1 day | |
| 114 | Grafana dashboard wired to Prometheus | 📅 1 day | [deps: #113] |
| 115 | Sentry error tracking — capture exceptions with full context (analysis ID, contract length, model) | 🕐 Half day | |
| 116 | Alerting — PagerDuty or OpsGenie for error spike, LLM API down, queue backup | 📅 1 day | [deps: #113, #115] |
| 117 | Uptime monitoring — external synthetic check on `/health` every 30s | ⚡ Quick | [deps: #49] |
| 118 | Cost dashboard — LLM spend per day/week, by analysis type, by user | 📅 1 day | [deps: #113, #61] |
| 119 | Log aggregation — ship structlog JSON to Loki or ELK | 📅 1 day | [deps: #111] |
| 120 | SLO definitions — 99.5% success rate, p95 < 10s analysis completion; alert on breach | 🕐 Half day | [deps: #113, #116] |

---

## Phase 10 — Frontend
> Week 6–8. Can be worked in parallel with backend phases after Phase 5 (auth) is done.
> Listed in dependency order — foundation items first, then features, then polish.

### Foundation
| # | Item | Effort | Notes |
|---|---|---|---|
| 96 | Adopt Shadcn/UI or Radix primitives — replace raw CSS with accessible component library | 📆 2–3 days | Do first; all other UI work builds on this |
| 80 | Zustand global state management — replace `useState` chains in `App.tsx` | 📅 1 day | |
| 79 | React Query or SWR for data fetching — caching, deduplication, background refetch | 📅 1 day | |
| 81 | Error boundaries — catch component crashes, show fallback UI instead of blank screen | 🕐 Half day | |
| 78 | SSE reconnect with exponential backoff — native `EventSource` has no retry; write wrapper | 📅 1 day | |
| 77 | Toast notifications for errors and successes | 🕐 Half day | [deps: #96] |
| 76 | Skeleton loading states instead of spinners | 🕐 Half day | [deps: #96] |
| 92 | Empty state designs — no contract submitted, no findings, no playbook versions | 🕐 Half day | |

### Core Features
| # | Item | Effort | Notes |
|---|---|---|---|
| 69 | File upload UI — drag-and-drop zone for PDF/DOCX; replaces paste-only input | 📅 1 day | [deps: backend #57–58] |
| 70 | In-browser PDF viewer — show rendered contract alongside findings | 📆 2–3 days | [deps: #69] |
| 71 | Clause highlighting — highlight found clauses directly in rendered contract text | 📆 2–3 days | [deps: #70, backend #18] |
| 72 | Findings filter panel — show only critical/high; filter by clause type | 🕐 Half day | |
| 73 | Export findings — PDF report, CSV, XLSX with full finding details | 📆 2–3 days | |
| 82 | Analysis history page — browse past analyses, re-open results | 📅 1 day | [deps: backend #43, #61] |
| 83 | Contract portfolio dashboard — risk score distribution, trend chart, clause frequency | 📆 2–3 days | [deps: #82, backend #38] |
| 84 | Playbook diff view — side-by-side comparison of two playbook versions with highlighted changes | 📆 2–3 days | |
| 85 | Rich text editor for playbook (CodeMirror or Monaco) with markdown table syntax highlighting | 📆 2–3 days | |
| 86 | Playbook import — upload DOCX/PDF playbook instead of paste | 📅 1 day | [deps: backend #57] |
| 87 | Batch upload UI — analyze multiple contracts, compare results in a table | 📆 2–3 days | [deps: backend #13, #39] |
| 88 | Finding feedback buttons — thumbs up/down; store in DB for LLM improvement loop | 🕐 Half day | [deps: backend #8, #61] |
| 89 | Shareable analysis link — `/analysis/{id}` permalink with optional auth gate | 📅 1 day | [deps: #61] |

### Polish & Accessibility
| # | Item | Effort | Notes |
|---|---|---|---|
| 74 | Dark mode — CSS variable theming | 📅 1 day | [deps: #96] |
| 75 | Mobile-responsive layout — current grid breaks below 768px | 📅 1 day | |
| 90 | Copy to clipboard — extracted values, recommendations, analysis ID | ⚡ Quick | |
| 91 | User onboarding flow — guided first analysis with a sample contract pre-loaded | 📅 1 day | |
| 93 | Keyboard shortcuts — Cmd+Enter to submit, Escape to clear, `/` to focus search | 🕐 Half day | |
| 94 | Accessibility — ARIA labels, focus management, screen reader support (WCAG 2.1 AA) | 📆 2–3 days | |
| 95 | Internationalization (i18n) — `react-i18next`; EN + DE as first two locales | 📆 2–3 days | |

---

## Phase 11 — Extended Testing
> Week 7–8. Builds on the test baseline from Phase 1. Some items require Phase 3 (RAG) and Phase 6 (backend arch) to be complete.

| # | Item | Effort | Notes |
|---|---|---|---|
| 123 | Integration tests — full pipeline with real SQLite + sample contracts; assert finding structure | 📅 1 day | |
| 133 | Test containers — replace SQLite integration tests with real Postgres via Testcontainers | 📅 1 day | [deps: #123] |
| 124 | RAG quality benchmarks — for each clause type, assert correct playbook chunk is retrieved | 📆 2–3 days | [deps: Phase 3] |
| 131 | RAGAS evaluation — measure faithfulness, answer relevance, context precision against golden dataset | 📆 2–3 days | [deps: Phase 3, #124] |
| 125 | Frontend unit tests — `App.tsx` analyze flow, `FindingsList` rendering, SSE event handling | 📅 1 day | |
| 134 | Visual regression tests — Percy or Chromatic on frontend component changes | 📅 1 day | [deps: #125] |
| 126 | End-to-end tests with Playwright — upload contract → see findings → export report | 📆 2–3 days | [deps: Phase 10] |
| 127 | Load tests — k6 or Locust; verify rate limiting, queue behavior under 50 concurrent analyses | 📅 1 day | [deps: Phase 6] |
| 128 | Contract tests — Pact API contract tests between frontend and backend; catch breaking changes | 📆 2–3 days | |
| 129 | Mutation testing via `mutmut` — verify test suite actually catches bugs | 📅 1 day | [deps: #121] |
| 130 | Property-based testing via `Hypothesis` — random contract text shapes, assert no crashes | 📅 1 day | |

---

## Phase 12 — DevOps & Infrastructure
> Week 8–10. Assumes CI/CD from Phase 1 is running.

| # | Item | Effort | Notes |
|---|---|---|---|
| 136 | Staging environment — auto-deploy every `main` merge to staging before prod | 📅 1 day | [deps: #135] |
| 137 | Blue/green or rolling deployments — zero-downtime; replaces `docker compose up -d` | 📆 2–3 days | [deps: #136] |
| 138 | Feature flags — Unleash or LaunchDarkly; ship incomplete features safely per org | 📅 1 day | [deps: Phase 5 auth] |
| 141 | Infrastructure as Code — Terraform for cloud resources; no more hand-configured servers | 🗓️ 1 week+ | |
| 142 | Kubernetes manifests + Helm chart for production deployment | 🗓️ 1 week+ | [deps: #141] |
| 143 | Horizontal Pod Autoscaler on worker deployment — scale on Celery queue depth metric | 📅 1 day | [deps: #142, #39] |
| 144 | Resource limits in container specs — `memory: 512Mi`, `cpu: 500m` prevent OOM-kills | ⚡ Quick | |
| 145 | Database backup automation — daily `pg_dump` to S3/Blob, 30-day retention, restore testing | 📅 1 day | |
| 146 | Disaster recovery runbook — step-by-step recovery from DB loss, Chroma corruption | 📅 1 day | |
| 147 | On-call runbook — what to do when LLM API is down, Chroma reindex fails, queue backs up | 📅 1 day | |

---

## Phase 13 — Product & Business Layer
> Week 10+. Requires the full backend, auth, and frontend stack to be complete.

| # | Item | Effort | Notes |
|---|---|---|---|
| 148 | Negotiation suggestions — generate specific redlined alternative clause for each risk finding | 📆 2–3 days | [deps: Phase 8 LLM work] |
| 149 | Precedent tracking — "this payment term appeared in 47 contracts; 12 were negotiated down" | 🗓️ 1 week+ | [deps: #82, #38] |
| 150 | Auto-suggest playbook updates — surface patterns from analyzed contracts to suggest playbook edits | 📆 2–3 days | [deps: #38, #83] |
| 151 | Multi-document comparison — analyze two contract versions, show risk profile delta | 📆 2–3 days | [deps: Phase 6 file upload] |
| 152 | Contract portfolio view — risk distribution, average clause values, trend over time | 📆 2–3 days | [deps: #83, #38] |
| 153 | External legal reference integration — link findings to relevant regulations or case law | 🗓️ 1 week+ | |
| 154 | Team collaboration — share analyses, add comments, assign review tasks | 🗓️ 1 week+ | [deps: Phase 5 auth] |
| 155 | Email / Slack / Teams notifications on analysis completion | 📅 1 day | [deps: #45 webhooks] |
| 156 | White-labeling — rebrandable UI and custom domain support for enterprise clients | 🗓️ 1 week+ | [deps: Phase 10, Phase 5] |
| 157 | Billing and usage tracking — per-org token consumption, monthly reports, overage alerts | 🗓️ 1 week+ | [deps: #118, Phase 5] |
| 158 | Freemium tier — limit free users to N analyses/month; track usage in DB | 📆 2–3 days | [deps: #157] |
| 159 | Audit-ready report export — formatted PDF with methodology, disclaimers, analysis metadata | 📆 2–3 days | [deps: #73] |
| 160 | Contract template library — pre-loaded sample contracts by type for onboarding and demos | 📅 1 day | |

---

## Dependency Graph Summary

```
Phase 0 (Quick Wins)
  └─► Phase 1 (Foundation + CI)
        └─► Phase 2 (DB Schema)
              ├─► Phase 3 (RAG + Extraction)
              │     └─► Phase 4 (Risk Scoring)
              └─► Phase 5 (Auth)
                    ├─► Phase 6 (Backend Arch)
                    │     ├─► Phase 7 (Security)
                    │     └─► Phase 8 (Advanced AI)  ◄── also needs Phase 3
                    └─► Phase 10 (Frontend)
                          └─► Phase 11 (Extended Testing) ◄── also needs Phases 3, 6
                                └─► Phase 12 (DevOps)
                                      └─► Phase 13 (Product)

Phase 9 (Observability) runs in parallel starting after Phase 0
```

---

## Total Effort Estimate

| Phase | Items | Rough Estimate |
|---|---|---|
| 0 — Quick Wins | 9 | 3–4 days |
| 1 — Dev Foundation | 8 | 1 week |
| 2 — DB Schema | 4 | 3–4 days |
| 3 — RAG + Extraction | 18 | 3–4 weeks |
| 4 — Risk Scoring | 6 | 1.5 weeks |
| 5 — Auth | 9 | 2 weeks |
| 6 — Backend Arch | 19 | 3–4 weeks |
| 7 — Security | 10 | 2 weeks |
| 8 — Advanced AI | 8 | 2 weeks |
| 9 — Observability | 9 | 1.5 weeks |
| 10 — Frontend | 28 | 4–5 weeks |
| 11 — Testing | 11 | 2–3 weeks |
| 12 — DevOps | 12 | 3–4 weeks |
| 13 — Product | 13 | 6–8 weeks |
| **Total** | **164** | **~9–12 months solo, ~3–4 months with a team of 3** |
