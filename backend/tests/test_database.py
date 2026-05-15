"""Unit tests for database.py — session lifecycle and schema registration."""
from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.database import Base, get_session  # noqa: E402


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def test_get_session_yields_async_session(test_engine, monkeypatch):
    """get_session context manager must yield an AsyncSession."""
    from backend.app import database as db_mod
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False, autocommit=False)
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)

    async with db_mod.get_session() as session:
        assert isinstance(session, AsyncSession)


async def test_get_session_rolls_back_on_exception(test_engine, monkeypatch):
    """get_session must roll back and re-raise when the body raises."""
    from backend.app import database as db_mod
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False, autocommit=False)
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)

    with pytest.raises(ValueError, match="boom"):
        async with db_mod.get_session() as _session:
            raise ValueError("boom")


def test_base_metadata_registers_expected_tables():
    """ORM metadata must include all core tables."""
    table_names = set(Base.metadata.tables.keys())
    assert "analyses" in table_names
    assert "playbook_versions" in table_names
    assert "playbook_chunks" in table_names
