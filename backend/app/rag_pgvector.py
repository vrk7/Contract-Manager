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
    async def reset_version(self, version_id: str, chunks: Iterable[tuple[str, str]]) -> None:
        chunks_list = list(chunks)
        if not chunks_list:
            return

        pool = await _get_pool()

        # Fetch existing content hashes to skip unchanged chunks.
        existing: dict[str, str] = {}
        rows = await pool.fetch(
            "SELECT chunk_id, content_hash FROM playbook_embeddings WHERE version_id = $1",
            version_id,
        )
        for row in rows:
            existing[row["chunk_id"]] = row["content_hash"]

        # Prune stale chunk IDs.
        current_ids = {cid for cid, _ in chunks_list}
        stale = [eid for eid in existing if eid not in current_ids]
        if stale:
            await pool.execute(
                "DELETE FROM playbook_embeddings WHERE version_id = $1 AND chunk_id = ANY($2::text[])",
                version_id,
                stale,
            )
            logger.debug("pgvector_embeddings_pruned", version_id=version_id, count=len(stale))

        # Only embed chunks whose content changed.
        new_chunks = [
            (cid, text)
            for cid, text in chunks_list
            if existing.get(cid) != _content_hash(text)
        ]
        if not new_chunks:
            logger.debug("pgvector_embeddings_unchanged", version_id=version_id)
            return

        texts = [text for _, text in new_chunks]
        vectors = await asyncio.to_thread(_embed, texts)

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO playbook_embeddings (chunk_id, version_id, content, content_hash, embedding)
                VALUES ($1, $2, $3, $4, $5::vector)
                ON CONFLICT (chunk_id, version_id) DO UPDATE
                  SET content = EXCLUDED.content,
                      content_hash = EXCLUDED.content_hash,
                      embedding = EXCLUDED.embedding
                """,
                [
                    (cid, version_id, text, _content_hash(text), str(vec))
                    for (cid, text), vec in zip(new_chunks, vectors)
                ],
            )
        logger.debug("pgvector_embeddings_upserted", version_id=version_id, count=len(new_chunks))

    async def query(self, version_id: str, text: str, k: int = 3) -> list[RetrievedChunk]:
        count = await self.collection_count(version_id)
        if count == 0:
            return []

        vec = (await asyncio.to_thread(_embed, [text]))[0]
        pool = await _get_pool()
        rows = await pool.fetch(
            """
            SELECT chunk_id, content,
                   (embedding <=> $1::vector) AS distance
            FROM playbook_embeddings
            WHERE version_id = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            str(vec),
            version_id,
            k,
        )
        retrieved: list[RetrievedChunk] = []
        for row in rows:
            if row["distance"] > _DISTANCE_THRESHOLD:
                logger.debug(
                    "pgvector_chunk_below_threshold",
                    chunk_id=row["chunk_id"],
                    distance=row["distance"],
                )
                continue
            retrieved.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    content=row["content"],
                    source="playbook",
                    playbook_version_id=version_id,
                )
            )
        return retrieved

    async def bm25_query(self, version_id: str, text: str, k: int = 3) -> list[RetrievedChunk]:
        try:
            from rank_bm25 import BM25Okapi as _BM25
        except ImportError:
            return []

        pool = await _get_pool()
        rows = await pool.fetch(
            "SELECT chunk_id, content FROM playbook_embeddings WHERE version_id = $1",
            version_id,
        )
        if not rows:
            return []

        ids = [r["chunk_id"] for r in rows]
        docs = [r["content"] for r in rows]
        tokenized = [doc.lower().split() for doc in docs]
        bm25 = _BM25(tokenized)
        scores = bm25.get_scores(text.lower().split())
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            RetrievedChunk(
                chunk_id=ids[i],
                content=docs[i],
                source="playbook",
                playbook_version_id=version_id,
            )
            for i in top
            if scores[i] > 0
        ]

    async def hybrid_query(self, version_id: str, text: str, k: int = 3) -> list[RetrievedChunk]:
        semantic, bm25 = await asyncio.gather(
            self.query(version_id, text, k=k),
            self.bm25_query(version_id, text, k=k),
        )
        seen: set[str] = {r.chunk_id for r in semantic}
        combined = list(semantic)
        for chunk in bm25:
            if chunk.chunk_id not in seen:
                combined.append(chunk)
                seen.add(chunk.chunk_id)
        return combined[:k]

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
