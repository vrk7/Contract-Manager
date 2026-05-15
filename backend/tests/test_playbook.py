"""Unit tests for playbook.py — version management and chunk persistence."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.database import Base  # noqa: E402
from backend.app.models import PlaybookChunk, PlaybookVersion  # noqa: E402
from backend.app.playbook import list_playbook_versions, persist_chunks, seed_playbook  # noqa: E402

_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session(tmp_path, monkeypatch):
    """Isolated in-memory SQLite session with RAG patched out."""
    from backend.app import rag as rag_mod
    monkeypatch.setattr(rag_mod.settings, "chroma_dir", str(tmp_path / "chroma"))

    engine = create_async_engine(_DB_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False, autocommit=False)
    async with factory() as s:
        yield s

    await engine.dispose()


@pytest.fixture
def playbook_file(tmp_path):
    """Temporary markdown playbook file."""
    p = tmp_path / "playbook.md"
    p.write_text("## Payment Terms\n\nPayment within 30 days.\n\n## Retainage\n\nMax 5%.")
    return str(p)
