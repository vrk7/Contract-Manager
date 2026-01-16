from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import chromadb
from chromadb import Settings as ChromaSettings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from .config import get_settings
from .schemas import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()


def chunk_playbook(content: str, size: int = 800) -> list[str]:
    words = content.split()
    chunks = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if len(" ".join(current)) >= size:
            chunks.append(" ".join(current))
            current = []
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

    def _collection(self, version_id: str):
        return self.client.get_or_create_collection(
            f"{self.collection_name}_{version_id}",
            embedding_function=self.embed_fn,
        )

    def collection_count(self, version_id: str) -> int:
        """
        Return the number of stored chunks for a playbook version.

        If the underlying collection cannot be read (for example after a fresh
        container start with a missing Chroma volume), fall back to zero so
        callers can decide to rebuild embeddings.
        """
        try:
            return self._collection(version_id).count()
        except Exception:
            logger.warning("Unable to read Chroma collection for version %s; treating as empty", version_id)
            return 0
            
    def reset_version(self, version_id: str, chunks: Iterable[tuple[str, str]]) -> None:
        collection = self._collection(version_id)
        try:
            collection.delete(where={"version_id": version_id})
        except Exception:
            # collection may be empty
            logger.debug("No existing embeddings to delete for %s", version_id)
        ids = []
        documents = []
        metadatas = []
        for chunk_id, text in chunks:
            ids.append(chunk_id)
            documents.append(text)
            metadatas.append({"version_id": version_id})
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, version_id: str, text: str, k: int = 3) -> list[RetrievedChunk]:
        collection = self._collection(version_id)
        if collection.count() == 0:
            return []
        result = collection.query(query_texts=[text], n_results=k)
        retrieved: list[RetrievedChunk] = []
        for idx, doc in enumerate(result["documents"][0]):
            retrieved.append(
                RetrievedChunk(
                    chunk_id=result["ids"][0][idx],
                    content=doc,
                    source="playbook",
                    playbook_version_id=version_id,
                )
            )
        return retrieved
