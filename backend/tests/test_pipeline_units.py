"""Unit tests for pipeline helper functions."""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.pipeline import (  # noqa: E402
    _compare_with_playbook,
    _merge_findings,
    _overall_risk,
    _split_into_sections,
    amplify_inter_clause_risks,
)
from backend.app.schemas import Finding, RetrievedChunk  # noqa: E402


def _chunk(content: str, chunk_id: str = "c1") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=content,
        source="playbook",
        playbook_version_id="v1",
    )


def _finding(clause_type: str, risk_level: str = "medium", extracted_value: str = "30 days") -> Finding:
    return Finding(
        clause_type=clause_type,
        extracted_value=extracted_value,
        playbook_standard="See playbook",
        deviation="None",
        risk_level=risk_level,
        recommendation="Review clause.",
        source_text="Contract text snippet.",
        retrieved_chunks=[_chunk("playbook text")],
    )


class TestCompareWithPlaybook:
    def test_payment_terms_critical_above_90(self):
        clause = {"clause_type": "payment_terms", "extracted_value": "91 days", "source_text": "pay within 91 days"}
        chunks = [_chunk("standard 30-60 days payment")]
        _, dev, risk = _compare_with_playbook(clause, chunks)
        assert risk == "critical"

    def test_payment_terms_high_61_to_90(self):
        clause = {"clause_type": "payment_terms", "extracted_value": "75 days", "source_text": "pay within 75 days"}
        chunks = [_chunk("standard 30-60 days net")]
        _, dev, risk = _compare_with_playbook(clause, chunks)
        assert risk == "high"

    def test_payment_terms_within_standard(self):
        clause = {"clause_type": "payment_terms", "extracted_value": "30 days", "source_text": "pay within 30 days"}
        chunks = [_chunk("standard 30-60 days payment")]
        _, dev, risk = _compare_with_playbook(clause, chunks)
        assert risk == "low"

    def test_retainage_critical_above_15(self):
        clause = {"clause_type": "retainage", "extracted_value": "20 %", "source_text": "retain 20%"}
        chunks = [_chunk("retainage max 10%")]
        _, _, risk = _compare_with_playbook(clause, chunks)
        assert risk == "critical"

    def test_retainage_high_above_10(self):
        clause = {"clause_type": "retainage", "extracted_value": "12 %", "source_text": "retain 12%"}
        chunks = [_chunk("retainage 5%")]
        _, _, risk = _compare_with_playbook(clause, chunks)
        assert risk == "high"

    def test_retainage_low_within_standard(self):
        clause = {"clause_type": "retainage", "extracted_value": "5 %", "source_text": "retain 5%"}
        chunks = [_chunk("retainage max 5%")]
        _, _, risk = _compare_with_playbook(clause, chunks)
        assert risk in ("low", "medium")

    def test_notice_period_critical_le3(self):
        clause = {"clause_type": "notice_period", "extracted_value": "3 days", "source_text": "within 3 days notice"}
        chunks = [_chunk("14-21 days notice")]
        _, _, risk = _compare_with_playbook(clause, chunks)
        assert risk == "critical"

    def test_indemnification_broad_form_critical(self):
        clause = {
            "clause_type": "indemnification",
            "extracted_value": "",
            "source_text": "indemnify regardless of fault",
        }
        chunks = [_chunk("proportionate fault only")]
        _, _, risk = _compare_with_playbook(clause, chunks)
        assert risk == "critical"

    def test_termination_notice_critical_lt7(self):
        clause = {
            "clause_type": "termination_notice",
            "extracted_value": "5 days",
            "source_text": "terminates upon 5 calendar days",
        }
        chunks = [_chunk("30+ days termination notice")]
        _, _, risk = _compare_with_playbook(clause, chunks)
        assert risk == "critical"


class TestMergeFindings:
    def test_single_finding_unchanged(self):
        findings = [_finding("payment_terms", "medium")]
        merged = _merge_findings(findings)
        assert len(merged) == 1

    def test_duplicate_clause_type_keeps_higher_risk(self):
        low = _finding("payment_terms", "low")
        high = _finding("payment_terms", "high")
        merged = _merge_findings([low, high])
        assert len(merged) == 1
        assert merged[0].risk_level == "high"

    def test_merge_combines_unique_chunks(self):
        f1 = _finding("payment_terms", "low")
        f1.retrieved_chunks = [_chunk("chunk A", "c1")]
        f2 = _finding("payment_terms", "high")
        f2.retrieved_chunks = [_chunk("chunk B", "c2")]
        merged = _merge_findings([f1, f2])
        chunk_ids = {c.chunk_id for c in merged[0].retrieved_chunks}
        assert chunk_ids == {"c1", "c2"}

    def test_different_clause_types_all_kept(self):
        findings = [
            _finding("payment_terms", "low"),
            _finding("retainage", "high"),
            _finding("indemnification", "critical"),
        ]
        merged = _merge_findings(findings)
        assert len(merged) == 3


class TestOverallRisk:
    def test_critical_dominates(self):
        findings = [_finding("a", "low"), _finding("b", "critical"), _finding("c", "medium")]
        assert _overall_risk(findings) == "critical"

    def test_no_findings_returns_unknown(self):
        assert _overall_risk([]) == "unknown"

    def test_all_low_returns_low(self):
        findings = [_finding("a", "low"), _finding("b", "low")]
        assert _overall_risk(findings) == "low"


class TestAmplifyInterClauseRisks:
    def test_high_payment_and_high_retainage_both_upgrade(self):
        findings = [
            _finding("payment_terms", "high"),
            _finding("retainage", "high"),
        ]
        result = amplify_inter_clause_risks(findings)
        risk_map = {f.clause_type: f.risk_level for f in result}
        assert risk_map["payment_terms"] == "critical"
        assert risk_map["retainage"] == "critical"

    def test_low_payment_and_high_retainage_no_upgrade(self):
        findings = [
            _finding("payment_terms", "low"),
            _finding("retainage", "high"),
        ]
        result = amplify_inter_clause_risks(findings)
        risk_map = {f.clause_type: f.risk_level for f in result}
        assert risk_map["payment_terms"] == "low"

    def test_single_finding_no_amplification(self):
        findings = [_finding("payment_terms", "high")]
        result = amplify_inter_clause_risks(findings)
        assert result[0].risk_level == "high"

    def test_already_critical_stays_critical(self):
        findings = [
            _finding("payment_terms", "critical"),
            _finding("retainage", "critical"),
        ]
        result = amplify_inter_clause_risks(findings)
        risk_map = {f.clause_type: f.risk_level for f in result}
        assert risk_map["payment_terms"] == "critical"


class TestSplitIntoSections:
    def test_small_text_returns_single_section(self):
        text = "Short contract text."
        assert _split_into_sections(text) == [text]

    def test_large_text_splits_into_multiple_sections(self):
        text = "Word " * 3000
        sections = _split_into_sections(text, max_size=500)
        assert len(sections) > 1

    def test_heading_based_split(self):
        text = (
            "ARTICLE 1 Payment terms apply here.\n"
            "ARTICLE 2 Retainage provisions follow.\n"
            "ARTICLE 3 Termination clauses end here.\n"
        )
        sections = _split_into_sections(text)
        assert len(sections) >= 2
