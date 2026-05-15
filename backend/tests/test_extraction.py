"""Unit tests for clause extraction — all 15 regex patterns in pipeline.py."""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.pipeline import _extract_clauses  # noqa: E402


def _types(text: str) -> set[str]:
    """Return the set of clause_types found in text."""
    return {f["clause_type"] for f in _extract_clauses(text)}


def _finding(text: str, clause_type: str) -> dict | None:
    """Return the first finding of a given clause_type, or None."""
    for f in _extract_clauses(text):
        if f["clause_type"] == clause_type:
            return f
    return None
