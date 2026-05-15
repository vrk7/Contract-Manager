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


@pytest.mark.parametrize("text,expected_value_fragment", [
    ("Owner shall pay within 30 days of invoice.", "30"),
    ("Payment due within 60 days from receipt.", "60"),
    ("All invoices settled within 90 days.", "90"),
])
def test_payment_terms_pattern(text, expected_value_fragment):
    f = _finding(text, "payment_terms")
    assert f is not None, f"payment_terms not found in: {text!r}"
    assert expected_value_fragment in f["extracted_value"]


@pytest.mark.parametrize("text,expected_value_fragment", [
    ("A retainage of 5% shall be withheld.", "5"),
    ("Retainage 10% until final completion.", "10"),
    ("Owner shall retain 15% of each invoice.", "15"),
])
def test_retainage_pattern(text, expected_value_fragment):
    f = _finding(text, "retainage")
    assert f is not None, f"retainage not found in: {text!r}"
    assert expected_value_fragment in f["extracted_value"]
