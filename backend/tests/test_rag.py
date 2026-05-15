"""Unit tests for rag.py — PlaybookRAG retrieval-augmented generation."""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.rag import PlaybookRAG, chunk_playbook  # noqa: E402

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
