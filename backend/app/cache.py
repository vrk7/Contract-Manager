"""Simple in-process analysis result cache keyed by contract+playbook hash."""
from __future__ import annotations

import hashlib
import threading
from typing import Any, Optional


class AnalysisCache:
    def __init__(self, max_entries: int = 256) -> None:
        self._store: dict[str, Any] = {}
        self._order: list[str] = []
        self._max = max_entries
        self._lock = threading.Lock()

    @staticmethod
    def make_key(contract_text: str, playbook_version_id: str, analysis_type: str) -> str:
        content = f"{analysis_type}:{playbook_version_id}:{contract_text}"
        return hashlib.sha256(content.encode(), usedforsecurity=False).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key not in self._store:
                if len(self._order) >= self._max:
                    evict = self._order.pop(0)
                    self._store.pop(evict, None)
                self._order.append(key)
            self._store[key] = value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._order.clear()


analysis_cache = AnalysisCache()
