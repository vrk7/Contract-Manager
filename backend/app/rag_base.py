from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from .schemas import RetrievedChunk


class BaseRAG(ABC):
    @abstractmethod
    async def collection_count(self, version_id: str) -> int: ...

    @abstractmethod
    async def reset_version(self, version_id: str, chunks: Iterable[tuple[str, str]]) -> None: ...

    @abstractmethod
    async def query(self, version_id: str, text: str, k: int = 3) -> list[RetrievedChunk]: ...

    @abstractmethod
    async def bm25_query(self, version_id: str, text: str, k: int = 3) -> list[RetrievedChunk]: ...

    @abstractmethod
    async def hybrid_query(self, version_id: str, text: str, k: int = 3) -> list[RetrievedChunk]: ...
