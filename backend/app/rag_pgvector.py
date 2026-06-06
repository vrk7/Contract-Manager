from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Iterable

import asyncpg
import structlog

from .config import get_settings
from .rag_base import BaseRAG
from .schemas import RetrievedChunk

logger = structlog.get_logger(__name__)
settings = get_settings()

# Cosine distance threshold (0 = identical, 2 = opposite).
# Corresponds to cosine_sim ≈ 0.35 (same effective floor as ChromaRAG L2 ≈ 1.2).
_DISTANCE_THRESHOLD: float = 0.65

_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
_EMBED_DIM = 384

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


def _pg_url(database_url: str) -> str:
    """Convert SQLAlchemy async DSN to plain asyncpg DSN."""
    url = database_url
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    _pg_url(settings.database_url),
                    min_size=1,
                    max_size=5,
                )
    return _pool


def _embed(texts: list[str]) -> list[list[float]]:
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=_EMBED_MODEL)
    return [[float(v) for v in vec] for vec in model.embed(texts)]


def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()[:12]  # nosec B324


class PgvectorRAG(BaseRAG):
    async def collection_count(self, version_id: str) -> int:
        pool = await _get_pool()
        try:
            row = await pool.fetchrow(
                "SELECT COUNT(*) AS n FROM playbook_embeddings WHERE version_id = $1",
                version_id,
            )
            return int(row["n"]) if row else 0
        except Exception:
            logger.warning("pgvector_collection_count_error", version_id=version_id)
            return 0
