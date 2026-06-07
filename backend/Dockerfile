FROM python:3.11.9-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first to leverage Docker layer caching.
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code.
COPY backend /app/backend
COPY standard_terms_playbook.md /app/standard_terms_playbook.md

ENV PYTHONPATH=/app
ENV PLAYBOOK_SEED_PATH=/app/standard_terms_playbook.md

COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations

ENV FASTEMBED_CACHE_PATH=/app/models

RUN python3 -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser && \
    mkdir -p /app/data/chroma && chown -R appuser:appgroup /app

USER appuser

CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
