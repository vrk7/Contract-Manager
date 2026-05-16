"""Tests for missing clause detection and new clause type patterns."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.pipeline import detect_missing_clauses, _extract_clauses  # noqa: E402
from backend.app.schemas import Finding, RetrievedChunk  # noqa: E402


def _finding(clause_type: str) -> Finding:
    return Finding(
        clause_type=clause_type,
        extracted_value="test",
        playbook_standard="standard",
        deviation="none",
        risk_level="low",
        recommendation="OK",
        source_text="text",
        retrieved_chunks=[
            RetrievedChunk(chunk_id="c1", content="chunk", source="playbook", playbook_version_id="v1")
        ],
    )


def test_all_required_clauses_present_no_warnings():
    required = ["payment_terms", "force_majeure", "limitation_of_liability",
                "indemnification", "dispute_resolution", "termination_notice"]
    findings = [_finding(ct) for ct in required]
    warnings = detect_missing_clauses(findings)
    missing = [w for w in warnings if w.type == "missing_clause"]
    assert missing == []


def test_missing_payment_terms_produces_warning():
    findings = [_finding("retainage")]
    warnings = detect_missing_clauses(findings)
    types = {w.triggered_by for w in warnings}
    assert "payment_terms" in types


def test_empty_findings_warns_all_required():
    warnings = detect_missing_clauses([])
    triggered = {w.triggered_by for w in warnings}
    assert "payment_terms" in triggered
    assert "force_majeure" in triggered
    assert "limitation_of_liability" in triggered


def test_missing_clause_warning_type():
    warnings = detect_missing_clauses([])
    assert all(w.type == "missing_clause" for w in warnings)


def _types(text: str) -> set[str]:
    return {f["clause_type"] for f in _extract_clauses(text)}


def test_non_compete_pattern():
    text = "Contractor agrees to a non-compete clause for 2 years post-contract."
    assert "non_compete" in _types(text)


def test_ip_assignment_pattern():
    text = "All work product is work made for hire and intellectual property shall be assigned to Owner."
    assert "ip_assignment" in _types(text)


def test_data_privacy_pattern():
    text = "Contractor must comply with GDPR and all personal data must be protected."
    assert "data_privacy" in _types(text)


def test_exclusivity_pattern():
    text = "Owner grants Contractor exclusive rights to supply all materials for this project."
    assert "exclusivity" in _types(text)


def test_cure_period_pattern():
    text = "The defaulting party shall have a cure period of 30 days to remedy the breach."
    f_list = [f for f in _extract_clauses(text) if f["clause_type"] == "cure_period"]
    assert len(f_list) > 0
    assert "30" in f_list[0]["extracted_value"]


def test_assignment_rights_pattern():
    text = "Contractor may not assign this agreement without prior written consent of Owner."
    assert "assignment_rights" in _types(text)
