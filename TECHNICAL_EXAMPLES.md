# Technical Implementation Examples - Deep Dive Answers

*Use these when the CTO asks "tell me more about..." or "how did you implement..."*

---

## 1. Multi-Step Data Pipeline (Contract Analyzer)

**When asked:** "How do you handle complex data processing?"

**Your Answer:**
"In my contract analyzer, I built a deterministic multi-step pipeline that processes contracts through several stages:

1. **Sanitization & Input Validation** (`guards.py`)
   - Content filtering for prompt injection attacks
   - Input length limits and rate limiting per IP
   - Structured schema validation with Pydantic

2. **Clause Extraction** (`pipeline.py`)
   - Regex + heuristic approach to identify contract clauses
   - Extracts section headers, terms, and obligations

3. **RAG Retrieval** (`rag.py`)
   - ChromaDB vector search with all-MiniLM-L6-v2 embeddings
   - Retrieves top-k relevant playbook chunks per clause
   - Attaches chunk metadata (source, version, similarity score)

4. **Deviation Analysis** (`llm.py`)
   - Claude Sonnet 4 API with streaming support
   - Compares contract clauses against playbook standards
   - Scores risk levels (low/medium/high/critical)

5. **Validation & Guardrails** (`guards.py`)
   - Drops findings missing source_text or retrieved_chunks
   - Emits guardrail warnings for ungrounded claims
   - Pydantic schema validation for type safety

6. **Streaming Response** (`events.py`)
   - Server-Sent Events (SSE) with structured JSON
   - Emits `status`, `partial_finding`, `final`, `error` events
   - Frontend receives real-time updates

**Why this matters for VOIDS:**
Your forecasting pipeline likely follows a similar pattern: ingest → clean → model inference → validation → recommendations. I understand how to build fault-tolerant, multi-step systems with proper error handling and observability."

---

## 2. Real-Time Streaming Architecture

**When asked:** "How did you implement SSE streaming?"

**Your Answer:**
"I chose SSE over WebSockets because the communication is unidirectional - server pushes updates to client. Here's the implementation:

**Backend (`events.py`):**
```python
async def stream_analysis_events(analysis_id: str):
    async for event in get_analysis_updates(analysis_id):
        yield f"data: {json.dumps(event)}\n\n"
```

**Frontend (`App.tsx`):**
```typescript
const eventSource = new EventSource(`/analysis/${id}/stream`);
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'partial_finding') {
    setFindings(prev => [...prev, data.finding]);
  }
};
```

**Benefits:**
- Users see progress immediately (better UX than waiting for batch results)
- Backend can process long-running tasks without blocking
- Automatic reconnection handling built into EventSource
- Works through standard HTTP/HTTPS (no WebSocket firewall issues)

**VOIDS parallel:**
When generating forecasts for hundreds of SKUs, streaming lets users see high-risk items first while lower-risk items are still calculating. Reduces perceived latency."

---

## 3. Database Design & Versioning

**When asked:** "How do you handle data persistence and versioning?"

**Your Answer:**
"I designed the database schema with three main concerns: audit trails, versioning, and performance.

**Schema (`models.py`):**
- `playbook_versions` table: immutable versions with content + change notes
- `playbook_chunks` table: chunked text with embeddings metadata
- `analyses` table: request params, results, status, timestamps
- `guardrail_warnings` table: validation failures for debugging

**Key patterns:**
1. **Immutable versioning:** Never update playbook content - create new versions
2. **Foreign keys:** Every analysis links to `playbook_version_id` used
3. **Async queries:** SQLAlchemy with `asyncpg` for non-blocking I/O
4. **Indexes:** Added indexes on `analysis_id`, `playbook_version_id`, `created_at`

**Example query (async):**
```python
async def get_analysis(analysis_id: str) -> Analysis:
    async with AsyncSession() as session:
        result = await session.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        return result.scalar_one_or_none()
```

**VOIDS parallel:**
Your forecasting system needs similar patterns:
- Immutable forecast snapshots for audit trails
- Link forecasts to the model version used
- Async queries for high throughput
- Indexes on `sku_id`, `date`, `forecast_date` for dashboard performance"

---

## 4. TypeScript Migration & Type Safety

**When asked:** "Tell me about your TypeScript experience"

**Your Answer:**
"I recently migrated my contract analyzer frontend from JavaScript to TypeScript to improve developer experience and catch bugs at compile time.

**Setup (`tsconfig.json`):**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "strict": true,
    "noUncheckedIndexedAccess": true
  }
}
```

**Key improvements:**
1. **Type-safe API responses:**
```typescript
interface AnalysisResponse {
  analysis_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  findings?: Finding[];
}

const response = await axios.get<AnalysisResponse>(`/analysis/${id}`);
// TypeScript knows response.data has these exact fields
```

2. **Component props with proper types:**
```typescript
interface FindingsListProps {
  findings: Finding[];
  onSelectFinding?: (finding: Finding) => void;
}

export const FindingsList: React.FC<FindingsListProps> = ({ findings }) => {
  // TypeScript ensures findings is always an array of Finding objects
};
```

3. **Enum types for constants:**
```typescript
enum RiskLevel {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  CRITICAL = 'critical'
}
```

**Benefits I saw:**
- Caught 12 bugs during migration (undefined checks, wrong prop types)
- Autocomplete in VSCode improved dramatically
- Refactoring became safer - rename a type, get errors everywhere it's used

**VOIDS parallel:**
Your TypeScript-first stack means I'll have the same safety guarantees. When dealing with forecast data structures (SKU, quantity, date ranges), type safety prevents runtime errors."

---

## 5. Performance Optimization

**When asked:** "How do you approach performance optimization?"

**Your Answer:**
"I follow a profile-first approach - measure before optimizing.

**Contract Analyzer optimizations:**

1. **Database connection pooling:**
```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True  # Check connections before use
)
```

2. **Async processing:**
   - FastAPI with `async def` endpoints
   - `asyncpg` for non-blocking database queries
   - Concurrent RAG retrieval for multiple clauses

3. **Caching embeddings:**
   - ChromaDB persists to disk - no re-embedding on restart
   - Playbook chunks embedded once per version

4. **Pagination hints in API design:**
   - Built with future pagination in mind
   - Can add `?limit=50&offset=100` easily

**At Kontex.dev:**
- Achieved 50% latency reduction through vector indexing optimization
- Profiled with `cProfile` and identified bottleneck in vector distance calculations
- Switched from brute-force search to approximate nearest neighbors (HNSW)

**VOIDS parallel:**
When displaying 1000+ SKU forecasts, you need:
- Database indexes on frequently queried columns
- Virtual scrolling in the UI (only render visible rows)
- Pre-aggregation for common queries (daily/weekly rollups)
- Caching for forecasts that don't change frequently"

---

## 6. Error Handling & Resilience

**When asked:** "How do you handle failures in production?"

**Your Answer:**
"I build systems that fail gracefully and provide observability.

**Error handling patterns:**

1. **LLM fallback for tests:**
```python
try:
    response = await claude_client.messages.create(...)
except Exception:
    # Offline heuristic fallback for tests
    return heuristic_analysis(contract_text)
```

2. **Structured error responses:**
```python
class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str
    timestamp: datetime
```

3. **Rate limiting with clear errors:**
```python
@limiter.limit("60/minute")
async def analyze_endpoint():
    # Returns 429 with Retry-After header
```

4. **Guardrail warnings (non-blocking):**
   - If a finding lacks grounding, emit warning but don't fail
   - Store warnings in database for debugging
   - Surface in API response: `{..., guardrail_warnings: [...]}`

5. **Database transaction rollback:**
```python
async with session.begin():
    # All queries in this block
    # Auto-rollback on exception
```

**Monitoring approach:**
- Log all analysis requests with IDs
- Track token usage and costs per request
- Store failed analyses with error details
- Health check endpoint: `GET /health`

**VOIDS parallel:**
Forecasting systems need similar resilience:
- Graceful degradation if ML model is slow (show cached forecasts)
- Clear error messages when data is missing ('No sales data for SKU X')
- Circuit breakers for external API calls (inventory systems)
- Alerting on forecast accuracy degradation"

---

## 7. Developer Experience Improvements

**When asked:** "What DX improvements have you driven?"

**Your Answer:**
"I focus on making local development fast and deployment repeatable.

**Improvements in Contract Analyzer:**

1. **One-command local setup:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

2. **Database flexibility:**
   - Defaults to SQLite for local dev (no DB setup required)
   - Switches to PostgreSQL in production via env var
   - Same code works in both environments

3. **Docker Compose for full stack:**
```bash
docker compose up -d  # Backend + Frontend + Postgres + Nginx
```

4. **Environment variables with examples:**
   - `.env.example` shows all required vars
   - Sensible defaults for local development

5. **Testing without API keys:**
   - Tests use offline LLM fallback
   - `pytest` works without `ANTHROPIC_API_KEY`

6. **TypeScript migration:**
   - Added `tsconfig.json` with strict mode
   - Converted components incrementally (no big-bang rewrite)
   - Added Vitest for unit tests

**VOIDS parallel:**
DX improvements I'd look for:
- Faster local startup (mock external services?)
- Better error messages in development
- Automated testing for critical paths (forecast accuracy)
- Type generation from database schema (Drizzle → TypeScript types)"

---

## 8. Working with AI/LLMs in Production

**When asked:** "How do you use LLMs in production systems?"

**Your Answer:**
"I treat LLMs as unreliable components that need guardrails and validation.

**Production patterns:**

1. **Structured outputs with Pydantic:**
```python
class ContractFinding(BaseModel):
    clause_text: str
    risk_level: Literal['low', 'medium', 'high', 'critical']
    deviation_description: str
    recommendation: str
    retrieved_chunks: List[str]
```

2. **Prompt engineering for reliability:**
   - Clear instructions: "Extract exactly N findings"
   - Examples in system prompt (few-shot)
   - Output format specification: "Return valid JSON"

3. **Token cost tracking:**
```python
usage = {
    'input_tokens': response.usage.input_tokens,
    'output_tokens': response.usage.output_tokens,
    'estimated_cost_usd': calculate_cost(response.usage)
}
```

4. **Streaming for better UX:**
```python
async with client.messages.stream(...) as stream:
    async for chunk in stream:
        yield parse_chunk(chunk)
```

5. **Grounding checks:**
   - Validate LLM output against retrieved chunks
   - Drop hallucinated findings
   - Emit warnings for suspicious outputs

**Cost optimization:**
- Use cheaper models for simple tasks (classification vs. generation)
- Cache common queries/responses
- Truncate input to max tokens while keeping relevant context

**VOIDS parallel:**
You likely use LLMs for:
- Forecast explanations ('Why is this SKU high risk?')
- Anomaly detection ('Unusual sales pattern detected')
- Recommendation generation ('Order 500 units from Supplier A')

Same patterns apply: structure outputs, validate against data, track costs."

---

## 9. Testing Strategy

**When asked:** "How do you test your code?"

**Your Answer:**
"I write tests that catch real bugs, not just increase coverage.

**Contract Analyzer test suite:**

1. **API integration tests:**
```python
@pytest.mark.asyncio
async def test_analyze_endpoint(client):
    response = await client.post('/analyze', json={
        'contract_text': 'Sample contract...',
        'analysis_type': 'risks'
    })
    assert response.status_code == 200
    assert 'analysis_id' in response.json()
```

2. **Guardrail validation tests:**
```python
def test_prompt_injection_detection():
    malicious_input = "Ignore previous instructions..."
    result = detect_injection(malicious_input)
    assert result.is_suspicious == True
```

3. **Rate limiting tests:**
```python
async def test_rate_limit_enforcement(client):
    for _ in range(61):  # Exceeds 60/min limit
        await client.post('/analyze', ...)
    assert last_response.status_code == 429
```

4. **Database transaction tests:**
```python
async def test_playbook_versioning():
    v1 = await create_version(content='Original')
    v2 = await create_version(content='Updated')
    assert v1.id != v2.id  # Immutable versions
```

**Testing philosophy:**
- Integration tests > unit tests (test real behavior)
- Mock external services (LLMs, third-party APIs)
- Test error paths (network failures, invalid input)
- Fast feedback (<10s for full test suite)

**VOIDS parallel:**
Critical tests for forecasting:
- Forecast accuracy tests (historical data vs. predictions)
- Edge cases (new SKU with no history, seasonal spikes)
- Data pipeline integrity (missing data handling)
- UI rendering tests (large SKU lists, chart performance)"

---

## 10. Deployment & DevOps

**When asked:** "Tell me about your deployment experience"

**Your Answer:**
"I own deployments end-to-end - from local development to production monitoring.

**Contract Analyzer deployment:**

1. **Infrastructure:**
   - AWS EC2 instance (t3.medium)
   - Docker Compose orchestrating 4 services
   - Nginx reverse proxy (HTTP/HTTPS)

2. **Deployment process:**
```bash
# On EC2 instance
git pull origin main
docker compose build
docker compose up -d
```

3. **Service architecture:**
   - `backend`: FastAPI on port 8000
   - `frontend`: Vite build served by Nginx
   - `db`: PostgreSQL 15 with persistent volume
   - `nginx`: Routes `/` → frontend, `/api` → backend

4. **Configuration management:**
   - Environment variables in `.env`
   - Secrets never in Git
   - Database credentials in environment

5. **Monitoring & health checks:**
   - `GET /health` endpoint for readiness probes
   - Log aggregation via `docker compose logs`
   - Database connection pre-ping for resilience

**Production lessons learned:**
- Always use volumes for database data (`./data:/var/lib/postgresql/data`)
- Health checks catch deployment failures early
- Nginx reverse proxy simplifies SSL setup (Certbot)

**VOIDS parallel:**
Your Vercel deployment is more managed, but same principles:
- Environment variables for secrets
- Health checks for service readiness
- Database connection pooling
- Logging for debugging production issues

I'm comfortable with both managed platforms (Vercel) and raw infrastructure (AWS EC2)."

---

## Key Takeaway

**When wrapping up any technical discussion:**

"What I love about building systems like this is solving real user problems with pragmatic engineering. My contract analyzer helps people negotiate better contracts. VOIDS helps D2C brands avoid stockouts and optimize cash flow.

The technical challenges are similar - complex data, simple UX, real-time updates, reliable predictions. I'm excited to apply everything I've learned to VOIDS's forecasting platform and help you scale from 300% growth to doubling ARR."

---

Use these examples to show depth when the CTO probes on specific topics. Don't memorize - understand the patterns and tell the story naturally.
