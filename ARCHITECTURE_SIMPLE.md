# Architecture — Simple Explanation

## What is this app?

You paste a construction contract into a webpage. The app reads through it, finds important clauses (like payment terms, penalties, warranties), compares them against your company's rulebook, and tells you what's risky and what to do about it.

---

## The 3 Main Parts

### 1. The Webpage (Frontend)
- Built with React (a popular way to build websites)
- Dark, professional design — deep navy background with frosted-glass panels and a purple accent color
- Has a login/register screen before you can use the app (accounts are stored in the database)
- Once logged in: two tabs — **Analyzer** and **Playbook**
- Has 4 key files:
  - `AuthPage.tsx` — the login/register screen
  - `App.tsx` — the main page with the text box, buttons, and results
  - `FindingsList.tsx` — shows each clause result with a color-coded risk badge
  - `api.ts` — handles talking to the backend (automatically adds your login token to every request)

### 2. The Server (Backend)
- Built with Python (FastAPI framework)
- Does all the heavy lifting: reading the contract, finding clauses, comparing to the rulebook, calling AI
- Lives in `backend/app/`

### 3. The Databases (Storage)
- **SQL Database** (SQLite locally, Postgres in Docker) — saves every analysis so you can look it up later
- **ChromaDB** — a special database that stores the rulebook in a way that lets you search it by *meaning*, not just exact words

---

## How the Pieces Connect

```
You (Browser)
  → create account / log in  →  receive a login token (JWT)
  → paste contract text
  → hit "Start Analysis" (token sent automatically with every request)
  → results appear one by one as they're found

Nginx (the doorman, port 80)
  → sends webpage requests to the Frontend
  → sends API requests to the Backend

Frontend (React, port 5173)
  → shows login screen if not authenticated
  → shows the main UI once logged in
  → sends your contract to the Backend with your token
  → listens for results in real time

Backend (FastAPI, port 8000)
  → verifies your login token
  → receives your contract
  → runs the analysis pipeline
  → reads/writes to SQL database
  → reads the rulebook from ChromaDB
  → calls Claude AI (for all 3 analysis modes)
  → streams results back to your browser
```

---

## What Happens Step by Step When You Click "Analyze"

### Step 1 — Your contract is sent to the server
- The backend immediately creates a record in the database saying "analysis queued"
- It sends back an ID right away (it doesn't make you wait)
- It starts processing your contract in the background

### Step 2 — Security check first
- Before anything else, the app scans your contract for sneaky text like *"ignore previous instructions"* or *"pretend to be"*
- This is called **prompt injection protection** — it stops people from tricking the AI
- Any suspicious text is replaced with `[filtered]`

### Step 3 — Finding clauses in your contract
- The app scans your contract using 15 search patterns (like a very smart CTRL+F)
- It looks for these specific clause types:

| Clause | What it looks for |
|---|---|
| Payment terms | "within 90 days" |
| Retainage | "retain 10%" |
| Notice period | "within 7 days notice" |
| Indemnification | "indemnify regardless of fault" |
| Termination notice | "termination within 3 calendar days" |
| Dispute resolution | "arbitration in New York" |
| Liquidated damages | "$5,000 per day" |
| Force majeure | "act of God / unforeseeable event" |
| Warranty | "warranty period of 2 years" |
| Insurance | "insurance coverage $1,000,000" |
| Change order | "change order markup of 15%" |
| Substantial completion | "substantial completion within 180 days" |
| Delay damages | "delay damages $10,000" |
| Governing law | "governed by the laws of California" |
| Limitation of liability | "liability shall not exceed $500,000" |

- If your contract is very long (over 30,000 characters, roughly 6 pages), it's split into overlapping chunks so nothing gets missed
- For each match, it also grabs the surrounding text (300 characters on each side) so there's context

### Step 4 — Looking up the rulebook
- For each clause found, it searches the **Playbook** (your company's standard terms)
- The Playbook is stored in ChromaDB as sentence-aware chunks (~800 characters each), each labelled with its section heading
- It uses **two search methods at once** and combines the results:
  - **Semantic search** — finds chunks that *mean* the same thing, even if the words are different
  - **BM25 keyword search** — finds chunks that share exact legal terms with the clause
- Top 3 unique chunks are kept (semantic results get priority)
- If nothing relevant is found in the playbook → that clause is skipped entirely

### Step 5 — Scoring the risk
- The app compares what the contract says vs. what the playbook says
- It uses simple rules to score risk. For example:
  - Payment terms > 90 days → **Critical**
  - Payment terms > 60 days → **High**
  - Payment terms within the standard → **Low**
  - Retainage > 15% → **Critical**
  - Notice period ≤ 3 days → **Critical**
  - Broad indemnification language → **Critical**
- It produces: what the playbook standard is, what the deviation is, and a risk level

### Step 6 — Calling Claude AI (all 3 modes)
- For **all three analysis types**, the app calls Claude (claude-sonnet-4-6)
- Claude is told to fill in a specific form (called a "tool") — this guarantees it always returns structured data, never free-form text:
  - **Risks mode** → fills in: risk level, deviation summary, recommendation, confidence score
  - **Summary mode** → fills in: plain-language description, key terms, whether it's a risk flag
  - **Obligations mode** → fills in: list of required actions, responsible party, deadline, consequence
- The retrieved playbook chunks are included in the prompt so Claude compares against your actual standards
- If no API key is set (like in tests), it returns empty placeholder values instead of calling Claude

### Step 7 — Cleaning up duplicates
- Some clauses might be found multiple times (especially in long contracts)
- The app keeps only the **highest-risk version** of each duplicate
- It merges the playbook references from all duplicates together

### Step 8 — Final safety check
- Any finding that is missing its original contract text or playbook reference is **dropped**
- This prevents made-up or unsupported results from showing up
- All the safety warnings are collected and shown to you at the end

### Step 9 — Results stream to your browser
- As each clause is processed, the result is immediately sent to your browser (you don't wait for all of them)
- Your browser receives 4 types of messages:
  - **status** — "extracting clauses...", "running analysis..."
  - **partial_finding** — one clause result, appears as each one finishes
  - **final** — the complete result with overall risk score
  - **error** — if something goes wrong
- This is called **SSE (Server-Sent Events)** — like a live news feed from the server to your browser

---

## The Playbook (Your Company's Rulebook)

- Stored as a markdown file: `standard_terms_playbook.md`
- Loaded into the database every time the server starts
- You can update it from the **Playbook tab** in the UI
- Every update creates a **new version** — old versions are never deleted (full history kept)
- When you update it, it's automatically split into chunks and re-indexed in ChromaDB
- You can also manually trigger a re-index via the API

---

## The 3 Analysis Modes Explained Simply

All three modes call Claude AI — the difference is what you ask it to focus on.

| Mode | What you get | What Claude fills in |
|---|---|---|
| **Summary** | Plain-language description of each clause + key terms | plain_language, key_terms, risk_flag |
| **Obligations** | Required actions, who's responsible, deadline, consequence | obligations[], party, deadline, consequence |
| **Risks** | Why it's risky, how it deviates from the playbook, negotiation advice, confidence score | risk_level, deviation_summary, recommendation, confidence |

---

## How Data is Saved

### SQL Database (4 tables)

**users table** — one row per registered account
- Stores: email, password (scrambled using bcrypt — never stored as plain text), active status, created date

**analyses table** — one row per analysis job
- Stores: the contract text, analysis type, status (queued / running / completed / failed), the full result, any safety warnings, token usage and cost, and which user ran it

**playbook_versions table** — one row per version of your rulebook
- Stores: the full markdown content, when it was created, a version label, a change note
- Versions are immutable — never edited, only new ones added

**playbook_chunks table** — one row per chunk of a playbook version
- Stores: the chunk text (with its section heading prepended), which version it belongs to

### ChromaDB (the smart search database)
- One collection per playbook version, e.g. `playbook_{version_id}_bge_small_v1`
- Uses a local AI model (`BAAI/bge-small-en-v1.5`, ~130 MB, downloaded once via fastembed) to turn text into numbers (embeddings)
- No external API needed for this — runs entirely on your machine
- When you search, it finds the 3 most semantically similar chunks
- If the model changes, the version tag in the collection name changes too — the old collection is left alone and a fresh one is built automatically

---

## Security

### Input Protection (before processing)
- Scans for 5 types of prompt injection attempts:
  - "ignore the previous instructions"
  - "system prompt"
  - "pretend to be"
  - "exfiltrate"
  - "unrelated task"
- Malicious text is replaced with `[filtered]`, not rejected — the rest of the contract still processes

### Output Protection (after processing)
- Any finding without a source quote from the contract → **dropped**
- Any finding without a matching playbook chunk → **dropped**
- This ensures every result shown to you is backed by real evidence

### Account & Login Security
- You must register and log in before using the app
- Passwords are never stored — only a bcrypt hash (a one-way scramble)
- After login you receive a **JWT token** (a signed string) that proves who you are
- Every request to the API includes this token in an `Authorization: Bearer` header — the server checks it without touching the database
- Tokens expire after 24 hours (configurable)
- The live results stream uses `?token=` in the URL because browsers can't send headers to a live stream
- Rate limiting: 60 requests/minute per IP on analyze and stream endpoints

---

## Running with Docker

4 containers run together:

| Container | What it does |
|---|---|
| `db` | Postgres database — starts first, others wait for it to be healthy |
| `backend` | Python FastAPI server on port 8000 |
| `frontend` | React app built and served by Nginx on port 5173 |
| `nginx` | The public-facing doorman on port 80/443, routes traffic to frontend or backend |

Two persistent storage volumes:
- `pgdata` — all your database records survive container restarts
- `chromadata` — all your embeddings survive container restarts (no need to re-index every time)

---

## Smart Engineering Choices (Why It's Built This Way)

### 1. Results appear as they're found, not all at once
Instead of waiting for the entire contract to be analyzed before showing anything, each clause result is sent to your browser the moment it's ready. This feels much faster for long contracts.

### 2. Claude is told to fill in a form, not write an essay
For all 3 modes, Claude is given a strict JSON "tool" schema and told it *must* fill it in. This guarantees the output is always structured and machine-readable — no more trying to parse free-form text with regex.

### 3. Two search methods are better than one
The rulebook search combines meaning-based (semantic) and keyword-based (BM25) search. Semantic search finds clauses paraphrased differently; BM25 catches exact legal terms. Together they miss fewer matches.

### 4. Logins don't hit the database on every request
Once you log in, you get a self-contained token (JWT) that the server can verify mathematically — without looking anything up in the database. This keeps the API fast and simple to scale.

### 5. Everything runs without a database in tests
Setting `BYPASS_DB_FOR_TESTS=true` makes the whole app run in memory with no database or ChromaDB needed. Tests run instantly with no setup.

### 6. The rulebook is versioned like code
Every time you update the playbook, the old version is kept forever. You can always see what standard was in place when a specific contract was analyzed.

### 7. No result shows up without evidence
The guardrail filter drops any finding that isn't backed by actual contract text and a matching playbook chunk. This prevents the AI from showing confident-looking results that aren't grounded in reality.

### 8. Everything is async
The server never blocks waiting for one thing to finish before starting another. Database reads, AI calls, and file operations all happen concurrently, making the server fast under load.
