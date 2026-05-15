from __future__ import annotations

import threading
from pathlib import Path
from typing import Iterable

import chromadb
import structlog
from chromadb import Settings as ChromaSettings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from .config import get_settings
from .schemas import RetrievedChunk

logger = structlog.get_logger(__name__)
settings = get_settings()


def chunk_playbook(content: str, max_chars: int = 800, overlap_sentences: int = 2) -> list[str]:
    """Split playbook content into sentence-aware chunks with sentence-level overlap.

    Each chunk stays under max_chars. The last overlap_sentences sentences of a chunk
    are prepended to the next chunk so context is not lost at boundaries.
    """
    import re as _re
    sentence_re = _re.compile(r"(?<=[.!?])\s+")
    sentences = [s.strip() for s in sentence_re.split(content.strip()) if s.strip()]
    if not sentences:
        return [content] if content.strip() else []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        slen = len(sentence)
        if current_len + slen + 1 > max_chars and current:
            chunks.append(" ".join(current))
            tail = current[-overlap_sentences:] if overlap_sentences else []
            current = list(tail)
            current_len = sum(len(s) + 1 for s in current)
        current.append(sentence)
        current_len += slen + 1

    if current:
        chunks.append(" ".join(current))
    return chunks


def get_chroma_client() -> chromadb.ClientAPI:
    Path(settings.chroma_dir).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=settings.chroma_dir,
        settings=ChromaSettings(
            allow_reset=True,
            # Telemetry is disabled by default to avoid runtime errors from the
            # PostHog client in certain environments. Can be enabled with
            # CHROMA_TELEMETRY=true if desired.
            anonymized_telemetry=settings.chroma_telemetry,
        ),
    )


class PlaybookRAG:
    def __init__(self, collection_name: str = "playbook") -> None:
        self.client = get_chroma_client()
        self.collection_name = collection_name
        self.embed_fn = DefaultEmbeddingFunction()
        self._lock = threading.Lock()

    def _collection(self, version_id: str):
        return self.client.get_or_create_collection(
            f"{self.collection_name}_{version_id}",
            embedding_function=self.embed_fn,  # type: ignore[arg-type]
        )

    def collection_count(self, version_id: str) -> int:
        """
        Return the number of stored chunks for a playbook version.

        If the underlying collection cannot be read (for example after a fresh
        container start with a missing Chroma volume), fall back to zero so
        callers can decide to rebuild embeddings.
        """
        with self._lock:
            try:
                return self._collection(version_id).count()
            except Exception:
                logger.warning("chroma_collection_unreadable", version_id=version_id)
                return 0

    def reset_version(self, version_id: str, chunks: Iterable[tuple[str, str]]) -> None:
        with self._lock:
            collection = self._collection(version_id)
            try:
                collection.delete(where={"version_id": version_id})
            except Exception:
                # collection may be empty
                logger.debug("no_embeddings_to_delete", version_id=version_id)
            ids = []
            documents = []
            metadatas = []
            for chunk_id, text in chunks:
                ids.append(chunk_id)
                documents.append(text)
                metadatas.append({"version_id": version_id})
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    # L2 distance above which a chunk is considered unrelated and dropped.
    # For unit-normalised embeddings, cosine_sim ≈ 0.35 ↔ L2 ≈ 1.14.
    _DISTANCE_THRESHOLD: float = 1.2

    def query(self, version_id: str, text: str, k: int = 3) -> list[RetrievedChunk]:
        with self._lock:
            collection = self._collection(version_id)
            if collection.count() == 0:
                return []
            result = collection.query(
                query_texts=[text], n_results=k, include=["documents", "distances"]
            )
        retrieved: list[RetrievedChunk] = []
        distances = result.get("distances", [[]])[0]
        for idx, doc in enumerate(result["documents"][0]):
            distance = distances[idx] if idx < len(distances) else 0.0
            if distance > self._DISTANCE_THRESHOLD:
                logger.debug(
                    "chunk_below_similarity_threshold",
                    chunk_id=result["ids"][0][idx],
                    distance=distance,
                )
                continue
            retrieved.append(
                RetrievedChunk(
                    chunk_id=result["ids"][0][idx],
                    content=doc,
                    source="playbook",
                    playbook_version_id=version_id,
                )
            )
        return retrieved
