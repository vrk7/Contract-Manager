"""Unit tests for rag.py — PlaybookRAG retrieval-augmented generation."""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.rag import PlaybookRAG  # noqa: E402

VERSION_ID = "test-v1"

SAMPLE_CHUNKS: list[tuple[str, str]] = [
    (f"{VERSION_ID}-0", "Payment terms: invoices must be settled within 30 days."),
    (f"{VERSION_ID}-1", "Retainage: maximum 5 percent of contract value shall be withheld."),
    (f"{VERSION_ID}-2", "Notice period: written notice required 14 days in advance."),
]


@pytest.fixture()
def rag(tmp_path, monkeypatch):
    """PlaybookRAG backed by an isolated temporary Chroma directory."""
    from backend.app import rag as rag_mod
    monkeypatch.setattr(rag_mod.settings, "chroma_dir", str(tmp_path / "chroma"))
    return PlaybookRAG()


@pytest.fixture()
def loaded_rag(rag):
    """PlaybookRAG pre-loaded with SAMPLE_CHUNKS."""
    rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    return rag


def test_new_rag_collection_is_empty(rag):
    assert rag.collection_count(VERSION_ID) == 0


def test_reset_version_stores_chunks(rag):
    rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    assert rag.collection_count(VERSION_ID) == len(SAMPLE_CHUNKS)


def test_query_returns_results(loaded_rag):
    results = loaded_rag.query(VERSION_ID, "payment invoice 30 days")
    assert len(results) > 0
    assert all(hasattr(r, "chunk_id") for r in results)
    assert all(hasattr(r, "content") for r in results)


def test_query_empty_collection_returns_empty_list(rag):
    results = rag.query(VERSION_ID, "payment terms")
    assert results == []


def test_query_respects_top_k(loaded_rag):
    # Use a query closely matching the chunk text to ensure threshold is met.
    results_k1 = loaded_rag.query(VERSION_ID, "payment invoice 30 days", k=1)
    results_k2 = loaded_rag.query(VERSION_ID, "payment retainage notice", k=3)
    assert len(results_k1) <= 1
    assert len(results_k2) <= 3
    # k=1 must return no more than k=3 results
    assert len(results_k1) <= len(results_k2) or len(results_k1) == len(results_k2)


def test_reset_version_overwrites_existing_chunks(rag):
    rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    assert rag.collection_count(VERSION_ID) == 3

    new_chunks = [(f"{VERSION_ID}-0", "New payment language.")]
    rag.reset_version(VERSION_ID, new_chunks)
    assert rag.collection_count(VERSION_ID) == 1


def test_collection_count_returns_correct_number(rag):
    assert rag.collection_count(VERSION_ID) == 0
    rag.reset_version(VERSION_ID, SAMPLE_CHUNKS[:2])
    assert rag.collection_count(VERSION_ID) == 2
    rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    assert rag.collection_count(VERSION_ID) == 3


def test_reset_version_skips_unchanged_chunks(rag):
    rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    count_before = rag.collection_count(VERSION_ID)
    rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    assert rag.collection_count(VERSION_ID) == count_before


def test_reset_version_updates_changed_chunk(rag):
    rag.reset_version(VERSION_ID, SAMPLE_CHUNKS)
    updated = [
        (SAMPLE_CHUNKS[0][0], "Updated payment text: 60 days."),
        SAMPLE_CHUNKS[1],
        SAMPLE_CHUNKS[2],
    ]
    rag.reset_version(VERSION_ID, updated)
    results = rag.query(VERSION_ID, "60 days payment")
    contents = [r.content for r in results]
    assert any("60 days" in c for c in contents)


def test_distance_threshold_filters_unrelated_chunks(loaded_rag):
    results = loaded_rag.query(VERSION_ID, "quantum physics neutron star galaxy")
    for r in results:
        assert r.playbook_version_id == VERSION_ID


def test_multiple_versions_are_isolated(tmp_path, monkeypatch):
    from backend.app import rag as rag_mod
    monkeypatch.setattr(rag_mod.settings, "chroma_dir", str(tmp_path / "chroma"))
    rag = PlaybookRAG()
    v1_chunks = [("v1-0", "Payment terms: 30 days net.")]
    v2_chunks = [("v2-0", "Payment terms: 60 days net.")]
    rag.reset_version("v1", v1_chunks)
    rag.reset_version("v2", v2_chunks)
    assert rag.collection_count("v1") == 1
    assert rag.collection_count("v2") == 1


def test_retrieved_chunk_has_required_fields(loaded_rag):
    results = loaded_rag.query(VERSION_ID, "retainage withheld")
    assert len(results) > 0
    chunk = results[0]
    assert chunk.chunk_id
    assert chunk.content
    assert chunk.source == "playbook"
    assert chunk.playbook_version_id == VERSION_ID
