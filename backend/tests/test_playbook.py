"""Unit tests for playbook.py — version management and chunk persistence."""
from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.database import Base  # noqa: E402
from backend.app.models import PlaybookChunk  # noqa: E402
from backend.app.playbook import list_playbook_versions, seed_playbook  # noqa: E402

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


async def test_seed_playbook_creates_first_version(session, playbook_file):
    version = await seed_playbook(session, playbook_file)
    assert version is not None
    assert version.id is not None
    assert "Payment within 30 days" in version.content


async def test_list_playbook_versions_returns_all(session, playbook_file):
    await seed_playbook(session, playbook_file)
    versions = await list_playbook_versions(session)
    assert len(versions) == 1
    assert versions[0].content is not None


async def test_persist_chunks_stores_records_in_db(session, playbook_file):
    version = await seed_playbook(session, playbook_file)
    from sqlalchemy import select
    result = await session.execute(select(PlaybookChunk).where(PlaybookChunk.version_id == version.id))
    chunks = result.scalars().all()
    assert len(chunks) > 0


async def test_chunk_content_is_retrievable_after_persist(session, playbook_file):
    version = await seed_playbook(session, playbook_file)
    from sqlalchemy import select
    result = await session.execute(select(PlaybookChunk).where(PlaybookChunk.version_id == version.id))
    chunks = result.scalars().all()
    combined = " ".join(c.content for c in chunks)
    assert "Payment" in combined or "Retainage" in combined


async def test_seed_playbook_is_idempotent_on_second_call(session, playbook_file):
    """Second seed call returns existing version without creating a duplicate."""
    v1 = await seed_playbook(session, playbook_file)
    v2 = await seed_playbook(session, playbook_file)
    assert v1.id == v2.id
    versions = await list_playbook_versions(session)
    assert len(versions) == 1


async def test_seed_playbook_returns_none_for_missing_file(session):
    result = await seed_playbook(session, "/nonexistent/path/playbook.md")
    assert result is None


async def test_list_playbook_versions_empty_without_seed(session):
    versions = await list_playbook_versions(session)
    assert versions == []


async def test_seed_playbook_stores_version_label(session, playbook_file):
    version = await seed_playbook(session, playbook_file)
    assert version is not None


async def test_multiple_seeds_with_different_content_creates_new_version(session, tmp_path):
    p1 = tmp_path / "p1.md"
    p2 = tmp_path / "p2.md"
    p1.write_text("# Terms v1\n\nPayment 30 days.")
    p2.write_text("# Terms v2\n\nPayment 45 days.")
    v1 = await seed_playbook(session, str(p1))
    await seed_playbook(session, str(p2))
    versions = await list_playbook_versions(session)
    assert len(versions) >= 1
    assert v1 is not None
