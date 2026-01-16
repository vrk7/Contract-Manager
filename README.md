# Contract Clause Analyzer Agent

### Author: Vysakh Ramakrishnan

FastAPI + React implementation of the multi-step, guardrailed Contract Clause Analyzer that compares construction contract clauses against the provided `standard_terms_playbook.md`, streams structured SSE results, and tracks token cost/usage.

**Live deployment:** http://35.178.58.160/

**Presentation:** https://docs.google.com/presentation/d/1syagMfZAZk1vYFDzh7qJbBLv2VNcMMkSyXZ231POVH4/edit?usp=sharing

The solution reads the playbook and example contracts in `sample_contracts/` and builds a deterministic pipeline: extract clauses → retrieve playbook chunks (Chroma RAG) → compare deviations → score risk → recommend negotiation positions → validate output schema and guardrails.

---

## Repository Layout

- `backend/` — FastAPI app, analysis pipeline, RAG utilities, guardrails, tests, Dockerfile.
- `frontend/` — Vite + React minimal UI with streaming results and playbook management.
- `sample_contracts/` — Provided example contracts used as fixtures.
- `standard_terms_playbook.md` — Source playbook; loaded into DB and embedded for retrieval.
- `deploy/nginx.conf` — Reverse proxy for Docker Compose deployment.
- `docker-compose.yml` — Backend + frontend + Postgres + Nginx stack.

---

## Running Locally

### Prerequisites

- Python 3.11+
- Node 18+
- `chromadb` downloads the `all-MiniLM-L6-v2` embedding model on first run (network required).

### Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

> **Having install issues?** Make sure you are using **Python 3.11+** before creating the virtual environment. Older Python versions (e.g., 3.8) will try to build `tokenizers` from source and can fail with missing build dependencies such as the mysterious `puccinialin` backend requirement some users see.
> 
> **Ubuntu 20.04 and missing `python3.11` package?** Install via [`uv`](https://github.com/astral-sh/uv) (works without PPAs):
> ```bash
> curl -LsSf https://astral.sh/uv/install.sh | sh
> uv python install 3.11
> uv venv --python 3.11 .venv
> ```
> Then activate with `source .venv/bin/activate` and continue with the steps above.
>
> **Still seeing install errors?** Delete any existing `.venv`, then rebuild the env with Python 3.11 and the pinned `tokenizers==0.22.1` from `backend/requirements.txt`:
> ```bash
> rm -rf .venv
> python3.11 -m venv .venv
> source .venv/bin/activate
> python -m pip install --upgrade pip
> python -m pip install -r backend/requirements.txt
> ```

Environment variables are defined in `.env.example`. Key values (sample `.env`):

```
# LLM
ANTHROPIC_API_KEY=sk-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Persistence + embeddings
DATABASE_URL=sqlite+aiosqlite:///./data/app.db   # or postgres+asyncpg://analyzer:analyzer@db:5432/analyzer
CHROMA_DIR=./data/chroma
PLAYBOOK_SEED_PATH=./standard_terms_playbook.md

# Rate limiting + debug
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_STREAM_PER_MINUTE=60
DEBUG_MODE=false

# Frontend -> backend base URL
VITE_API_BASE=http://localhost:8000
```

- `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` – Claude via official SDK (optional; offline heuristic fallback used in tests).
- `DATABASE_URL` – defaults to Postgres (`postgres+asyncpg://...`) targeting the `db` service in `docker-compose` (and automatically when running inside the container); outside Docker, the app falls back to SQLite unless you set `DATABASE_URL` yourself.
- `CHROMA_DIR` – persistent embedding store.
- `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_STREAM_PER_MINUTE` – slowapi per-IP throttles.

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host --port 5173
```

Set `VITE_API_BASE` to point to the backend (e.g., `http://localhost:8000`).

---

## API Surface

- `POST /analyze` → `{analysis_id,status}` (async background run). Request: `{contract_text, analysis_type: risks|summary|obligations, playbook_version_id?}`.
- `GET /analysis/{id}` → final validated result or status.
- `GET /analysis/{id}/stream` → SSE streaming with JSON payloads (`status`, `partial_finding`, `final`, `error`).
- `GET /playbook` / `GET /playbook/versions` / `GET /playbook/versions/{id}` — view playbook content and versions.
- `PUT /playbook` — create a new version (content + optional change note).
- `POST /playbook/reindex` — rebuild embeddings for a version.
- `GET /health` — health probe.

Response schema includes `playbook_version_id`, `guardrail_warnings`, `retrieved_chunks[{chunk_id,content,source,playbook_version_id}]`, and `usage{input_tokens,output_tokens,total_tokens,estimated_cost_usd}` per request.

---

## Agent Architecture & Guardrails

- **Multi-step pipeline:** sanitize → clause extraction → RAG retrieval (Chroma) → deviation scoring vs playbook text → LLM validation (Claude SDK, heuristic fallback) → Pydantic validation → guardrail pruning of ungrounded findings.
- **Playbook grounding:** playbook ingested from file/DB, chunked, and embedded; retrieval attaches chunk metadata to every finding.
- **Guardrails:** content filtering for prompt injection, strict Pydantic schema validation, per-IP rate limiting (slowapi), and grounding checks (drop findings missing source_text or retrieved_chunks, emit warnings).
- **Streaming:** SSE emits structured JSON-only events.
- **Cost tracking:** token estimates recorded per analysis and surfaced in API/UI.
- **Storage:** analyses, guardrail warnings, and usage stored in SQLite/Postgres; embeddings persisted in Chroma dir.

---

## Frontend Features

- Paste/upload contract text, pick analysis type, kick off async analysis.
- Live SSE stream of findings with risk badges and guardrail warnings.
- Usage/cost display.
- Playbook management: view current content, edit/save new version (versioning), list versions, trigger reindex, select version for analysis.

---

## Testing

Pytest suite covers API health, async analyze lifecycle, guardrail injection detection, and rate limiting.

```bash
source .venv/bin/activate
pytest backend/tests
```

Tests use the provided playbook and run against SQLite with offline LLM fallback.

---

## Deployment (AWS EC2 + Docker Compose)

### Server naming convention

Use the pattern `<app>-<surface>-<env>-<role>-<region-zone>-<nn>` for hosts that run this stack:

- **app:** top-level product or codename (e.g., `arctis`).
- **surface:** the primary interface or subsystem (e.g., `api`).
- **env:** environment (`dev`, `stg`, `prod`).
- **role:** workload role on the host (`web`, `worker`, `db`, etc.).
- **region-zone:** cloud region and zone without punctuation (`eu-west-2b` → `euw2b`).
- **nn:** zero-padded sequence number for horizontal instances.

Example: `arctis-api-prod-web-euw2b-01` follows this convention (`arctis` app, API surface, production web role, AWS `eu-west-2b`, first node).

1. Get onto your server and pull the code
   1. Create an SSH key if missing (`ssh-keygen -t ed25519 -C "your-mail@example.com"` — generates keypair).
   2. Add the public key to the cloud VM via the provider console (AWS EC2 key pairs or equivalent — allows SSH access).
   3. SSH into the VM (example: `ssh ubuntu@35.178.58.160`; opens remote shell).
   4. Install Git if missing (Ubuntu example: `sudo apt update && sudo apt install -y git` — refreshes package index then installs Git).
   5. Clone the repository.
2. Go to the project folder
   1. `cd /founding-eng-takehome` or the appropriate clone location (move into the project directory).
3. Make the environment file
   1. Create `.env` in the project root using `nano` or `vi` (open a new env file in an editor).
   2. Include:
      - `ANTHROPIC_API_KEY`
      - `DATABASE_URL=postgres+asyncpg://analyzer:analyzer@db:5432/analyzer`
      - `RATE_LIMIT_PER_MINUTE=60`
      - `RATE_LIMIT_STREAM_PER_MINUTE=60`
      - `PLAYBOOK_SEED_PATH=/app/standard_terms_playbook.md`
   3. Note that these match `docker-compose` defaults.
   4. Save and exit the editor.
4. Install Docker and Docker Compose
   1. Update packages: `sudo apt update` (refresh package index).
   2. Install dependencies: `sudo apt install -y ca-certificates curl gnupg` (tools for secure repository setup).
   3. Add Docker’s GPG key: `sudo install -m 0755 -d /etc/apt/keyrings && sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.gpg && sudo chmod a+r /etc/apt/keyrings/docker.gpg` (trust Docker packages).
   4. Add the repository: `echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null` (enable Docker apt repo).
   5. Install Docker Engine and Compose: `sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin` (install container runtime and compose plugin).
   6. Add your user to the Docker group: `sudo usermod -aG docker $USER` (log out/in to apply; allows docker without sudo).
   7. Adjust steps as needed for non-Ubuntu OSes.
5. Build and start the stack
   1. Run `docker compose build` (build container images).
   2. Run `docker compose up -d` (start stack in the background).
   3. Services: Postgres (`db`), FastAPI backend (8000), frontend via Nginx (80/443).
6. Find your server IP and open the app
   1. Get the public IP from the cloud console.
   2. Open `http://35.178.58.160` in the browser (reach the app).
   3. Nginx routes `/` to the frontend and `/api` to the backend.
   4. Verify backend health at `http://35.178.58.160:8000/health`.
   5. Want a direct backend URL? Keep port 8000 open or add a reverse-proxy path; use `http://35.178.58.160:8000/docs` for the FastAPI docs.
   6. Running `uvicorn backend.app.main:app --reload` locally without Docker? Either set `DATABASE_URL` to your Postgres instance (e.g., `postgres+asyncpg://user:pass@localhost:5432/dbname`) or let the default local fallback use SQLite (`sqlite+aiosqlite:///./data/app.db`). If you see `Temporary failure in name resolution` or `password authentication failed` on startup, your `DATABASE_URL` is pointing at an unreachable/unauthorized Postgres host—switch to a reachable URL or the SQLite fallback.
7. First-run notes
   1. `standard_terms_playbook.md` is seeded and chunked automatically.
8. Use the app
   1. Paste contract text, choose analysis type, start analysis.
   2. In the Playbook tab: save a new version, reindex, select a version for analysis.
9. Logs and health checks
   1. `docker compose logs -f backend frontend nginx` (tail service logs).
   2. `docker compose exec db pg_isready` (check Postgres readiness).
10. (Optional) Set up a domain
    1. Create a DNS A record pointing to the server IP.
    2. Note DNS propagation delay.
11. (Optional) Enable HTTPS with Certbot
    1. Install Certbot (Ubuntu example: `sudo apt install -y certbot python3-certbot-nginx` — adds certificate tool).
    2. Run Certbot with domain flags: `sudo certbot --nginx -d your.domain.com -d www.your.domain.com` (request and install certificates).
    3. Certbot may update Nginx automatically.
12. How to edit `deploy/nginx.conf`
    1. Open the file.
    2. Example SSL directives:
       - `listen 443 ssl;`
       - `ssl_certificate /etc/letsencrypt/live/your.domain.com/fullchain.pem;`
       - `ssl_certificate_key /etc/letsencrypt/live/your.domain.com/privkey.pem;`
    3. Keep existing `/` and `/api` locations unchanged.
    4. Restart Nginx with `docker compose restart nginx`.
13. Restart or stop
    1. `docker compose restart`.
    2. `docker compose down`.

The app should be reachable via HTTP or HTTPS depending on configuration.

> Notes
> - Nginx listens on 80/443 and proxies to backend/frontend containers. Opening port 8000 is optional (direct backend access) but not required for the proxied stack.

---

## How the Playbook is Used

- On startup the backend seeds the latest playbook version from `standard_terms_playbook.md`, chunks it, stores versions/chunks in the DB, and embeds chunks into Chroma.
- Each analysis retrieves relevant chunks per clause and includes them in `retrieved_chunks`. If grounding is missing, the finding is dropped and a guardrail warning is emitted.
- Playbook updates create immutable versions; analyses record the version used.

## Data storage and analysis results

- Analyses, playbook versions, and guardrail warnings are persisted in the Postgres database by default (`DATABASE_URL`).
- The async SQLAlchemy models in `backend/app/models.py` handle saving analysis requests and results; no extra setup is required beyond a reachable Postgres instance.
- For local, single-user experimentation you can swap `DATABASE_URL` to SQLite (e.g., `sqlite+aiosqlite:///./data/app.db`), but production/deployments should use Postgres.
---

## What to Improve Next

- Deeper clause extraction coverage (NER/regex hybrid and model-assisted spans).
- Richer deviation calculations parsed directly from playbook tables instead of heuristics.
- Move background processing to a task queue (Celery/RQ) for higher throughput.
- Add CI/CD and IaC for cloud reproducibility.

---
