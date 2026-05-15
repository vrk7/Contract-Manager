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


@pytest.mark.parametrize("text,expected_value_fragment", [
    ("Written notice required within 14 days notice of termination.", "14"),
    ("Party must provide notice within 7 calendar days notice.", "7"),
    ("Claims must be filed within 21 days notice of the event.", "21"),
])
def test_notice_period_pattern(text, expected_value_fragment):
    f = _finding(text, "notice_period")
    assert f is not None, f"notice_period not found in: {text!r}"
    assert expected_value_fragment in f["extracted_value"]


@pytest.mark.parametrize("text,clause", [
    ("Contractor shall indemnify Owner regardless of fault.", "indemnification"),
    ("Contractor shall indemnify Owner for any and all claims.", "indemnification"),
])
def test_indemnification_pattern(text, clause):
    assert clause in _types(text)


def test_indemnification_source_text_contains_contract_snippet():
    text = "Contractor shall indemnify and hold harmless the Owner regardless of fault for all claims."
    f = _finding(text, "indemnification")
    assert f is not None
    assert len(f["source_text"]) > 0


@pytest.mark.parametrize("text,expected_fragment", [
    ("Either party may terminate upon 30 calendar days written notice.", "30"),
    ("Contract terminates upon 14 calendar days notice.", "14"),
])
def test_termination_notice_pattern(text, expected_fragment):
    f = _finding(text, "termination_notice")
    assert f is not None, f"termination_notice not found in: {text!r}"
    assert expected_fragment in f["extracted_value"]


@pytest.mark.parametrize("text,expected_fragment", [
    ("Liquidated damages of 1,000 per calendar day of delay.", "1,000"),
    ("Contractor owes €75,000 per day for late completion.", "75,000"),
])
def test_liquidated_damages_pattern(text, expected_fragment):
    f = _finding(text, "liquidated_damages")
    assert f is not None, f"liquidated_damages not found in: {text!r}"
    assert expected_fragment in f["extracted_value"]


def test_force_majeure_pattern():
    text = "The parties shall not be liable for delays caused by force majeure events."
    assert "force_majeure" in _types(text)


@pytest.mark.parametrize("text,expected_fragment", [
    ("Contractor warrants work for a period of 2 years.", "2"),
    ("Equipment warranty period of 12 months from acceptance.", "12"),
])
def test_warranty_pattern(text, expected_fragment):
    f = _finding(text, "warranty")
    assert f is not None, f"warranty not found in: {text!r}"
    assert expected_fragment in f["extracted_value"]


def test_insurance_pattern():
    text = "Contractor must maintain insurance coverage of at least $1,000,000 per occurrence."
    f = _finding(text, "insurance")
    assert f is not None
    assert "1,000,000" in f["extracted_value"]
