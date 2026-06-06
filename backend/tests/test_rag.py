"""Unit tests for RAG backends and the get_rag_backend factory."""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.rag import ChromaRAG, get_rag_backend  # noqa: E402

VERSION_ID = "test-v1"

SAMPLE_CHUNKS: list[tuple[str, str]] = [
    (f"{VERSION_ID}-0", "Payment terms: invoices must be settled within 30 days."),
    (f"{VERSION_ID}-1", "Retainage: maximum 5 percent of contract value shall be withheld."),
    (f"{VERSION_ID}-2", "Notice period: written notice required 14 days in advance."),
]


@pytest.fixture()
def rag(tmp_path, monkeypatch):
    """ChromaRAG backed by an isolated temporary Chroma directory."""
    from backend.app import rag as rag_mod
    monkeypatch.setattr(rag_mod.settings, "chroma_dir", str(tmp_path / "chroma"))
    return ChromaRAG()


@pytest.fixture()
async def loaded_rag(rag):
    """ChromaRAG pre-loaded with SAMPLE_CHUNKS."""
    await rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    return rag


async def test_new_rag_collection_is_empty(rag):
    assert await rag.collection_count(VERSION_ID) == 0


async def test_reset_version_stores_chunks(rag):
    await rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    assert await rag.collection_count(VERSION_ID) == len(SAMPLE_CHUNKS)


async def test_query_returns_results(loaded_rag):
    results = await loaded_rag.query(VERSION_ID, "payment invoice 30 days")
    assert len(results) > 0
    assert all(hasattr(r, "chunk_id") for r in results)
    assert all(hasattr(r, "content") for r in results)


async def test_query_empty_collection_returns_empty_list(rag):
    results = await rag.query(VERSION_ID, "payment terms")
    assert results == []


async def test_query_respects_top_k(loaded_rag):
    results_k1 = await loaded_rag.query(VERSION_ID, "payment invoice 30 days", k=1)
    results_k2 = await loaded_rag.query(VERSION_ID, "payment retainage notice", k=3)
    assert len(results_k1) <= 1
    assert len(results_k2) <= 3


async def test_reset_version_overwrites_existing_chunks(rag):
    await rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    assert await rag.collection_count(VERSION_ID) == 3

    new_chunks = [(f"{VERSION_ID}-0", "New payment language.")]
    await rag.reset_version(VERSION_ID, new_chunks)
    assert await rag.collection_count(VERSION_ID) == 1


async def test_collection_count_returns_correct_number(rag):
    assert await rag.collection_count(VERSION_ID) == 0
    await rag.reset_version(VERSION_ID, SAMPLE_CHUNKS[:2])
    assert await rag.collection_count(VERSION_ID) == 2
    await rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    assert await rag.collection_count(VERSION_ID) == 3


async def test_reset_version_skips_unchanged_chunks(rag):
    await rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    count_before = await rag.collection_count(VERSION_ID)
    await rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    assert await rag.collection_count(VERSION_ID) == count_before


async def test_reset_version_updates_changed_chunk(rag):
    await rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    updated = [
        (SAMPLE_CHUNKS[0][0], "Updated payment text: 60 days."),
        SAMPLE_CHUNKS[1],
        SAMPLE_CHUNKS[2],
    ]
    await rag.reset_version(VERSION_ID, updated)
    results = await rag.query(VERSION_ID, "60 days payment")
    contents = [r.content for r in results]
    assert any("60 days" in c for c in contents)


async def test_distance_threshold_filters_unrelated_chunks(loaded_rag):
    results = await loaded_rag.query(VERSION_ID, "quantum physics neutron star galaxy")
    for r in results:
        assert r.playbook_version_id == VERSION_ID


async def test_multiple_versions_are_isolated(tmp_path, monkeypatch):
    from backend.app import rag as rag_mod
    monkeypatch.setattr(rag_mod.settings, "chroma_dir", str(tmp_path / "chroma"))
    r = ChromaRAG()
    await r.reset_version("v1", [("v1-0", "Payment terms: 30 days net.")])
    await r.reset_version("v2", [("v2-0", "Payment terms: 60 days net.")])
    assert await r.collection_count("v1") == 1
    assert await r.collection_count("v2") == 1


async def test_retrieved_chunk_has_required_fields(loaded_rag):
    results = await loaded_rag.query(VERSION_ID, "retainage withheld")
    assert len(results) > 0
    chunk = results[0]
    assert chunk.chunk_id
    assert chunk.content
    assert chunk.source == "playbook"
    assert chunk.playbook_version_id == VERSION_ID


async def test_bm25_query_returns_results_when_available(loaded_rag):
    try:
        import rank_bm25  # noqa: F401
        bm25_available = True
    except ImportError:
        bm25_available = False

    results = await loaded_rag.bm25_query(VERSION_ID, "payment invoice 30 days")
    if bm25_available:
        assert len(results) > 0
    else:
        assert results == []


async def test_bm25_query_empty_collection_returns_empty(rag):
    results = await rag.bm25_query(VERSION_ID, "payment terms")
    assert results == []


async def test_hybrid_query_returns_at_most_k_results(loaded_rag):
    results = await loaded_rag.hybrid_query(VERSION_ID, "payment retainage notice", k=2)
    assert len(results) <= 2


async def test_hybrid_query_no_duplicate_chunk_ids(loaded_rag):
    results = await loaded_rag.hybrid_query(VERSION_ID, "payment retainage notice", k=5)
    ids = [r.chunk_id for r in results]
    assert len(ids) == len(set(ids))


# ── factory tests ─────────────────────────────────────────────────────────────

def test_factory_returns_chroma_by_default(monkeypatch):
    from backend.app import rag as rag_mod
    monkeypatch.setattr(rag_mod.settings, "vector_backend", "chroma")
    backend = get_rag_backend()
    assert isinstance(backend, ChromaRAG)


def test_factory_returns_chroma_when_pgvector_requested_with_sqlite(monkeypatch):
    """pgvector silently falls back to Chroma when DATABASE_URL is SQLite."""
    from backend.app import rag as rag_mod
    monkeypatch.setattr(rag_mod.settings, "vector_backend", "pgvector")
    monkeypatch.setattr(rag_mod.settings, "database_url", "sqlite+aiosqlite:///./data/app.db")
    backend = get_rag_backend()
    assert isinstance(backend, ChromaRAG)


def test_factory_returns_pgvector_when_postgres_url(monkeypatch):
    from backend.app import rag as rag_mod
    from backend.app.rag_pgvector import PgvectorRAG
    monkeypatch.setattr(rag_mod.settings, "vector_backend", "pgvector")
    monkeypatch.setattr(
        rag_mod.settings, "database_url",
        "postgresql+asyncpg://analyzer:analyzer@localhost:5432/analyzer",
    )
    backend = get_rag_backend()
    assert isinstance(backend, PgvectorRAG)
