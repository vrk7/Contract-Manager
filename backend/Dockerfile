FROM python:3.11.9-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

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

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser && \
    mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser

CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
