"""Tests for Pydantic schema validation."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from pydantic import ValidationError

from backend.app.schemas import AnalysisCreateRequest, Finding


MINIMAL_TEXT = "Sample contract text that is long enough."

_FINDING_DEFAULTS = dict(
    clause_type="payment_terms",
    extracted_value="30 days",
    playbook_standard="Net 30",
    deviation="None",
    risk_level="low",
    recommendation="Acceptable.",
    source_text="Payment terms are 30 days.",
)


class TestAnalysisCreateRequest:
    def test_valid_risks(self):
        req = AnalysisCreateRequest(contract_text=MINIMAL_TEXT, analysis_type="risks")
        assert req.analysis_type == "risks"

    def test_valid_summary(self):
        req = AnalysisCreateRequest(contract_text=MINIMAL_TEXT, analysis_type="summary")
        assert req.analysis_type == "summary"

    def test_valid_obligations(self):
        req = AnalysisCreateRequest(contract_text=MINIMAL_TEXT, analysis_type="obligations")
        assert req.analysis_type == "obligations"

    def test_contract_text_stripped(self):
        req = AnalysisCreateRequest(contract_text="  " + MINIMAL_TEXT + "  ", analysis_type="risks")
        assert req.contract_text == MINIMAL_TEXT

    def test_empty_contract_text_raises(self):
        with pytest.raises(ValidationError):
            AnalysisCreateRequest(contract_text="", analysis_type="risks")

    def test_invalid_analysis_type_raises(self):
        with pytest.raises(ValidationError):
            AnalysisCreateRequest(contract_text=MINIMAL_TEXT, analysis_type="invalid_type")

    def test_short_text_raises(self):
        with pytest.raises(ValidationError):
            AnalysisCreateRequest(contract_text="short", analysis_type="risks")


class TestFindingSchema:
    def test_minimal_finding(self):
        f = Finding(**_FINDING_DEFAULTS)
        assert f.clause_type == "payment_terms"
        assert f.risk_level == "low"
        assert f.confidence == 0.5

    def test_full_finding(self):
        f = Finding(
            clause_type="retainage",
            risk_level="medium",
            extracted_value="10%",
            deviation="Above 5% standard",
            playbook_standard="5% retainage cap",
            recommendation="Negotiate down to 5%",
            source_text="Retainage shall be 10%",
            confidence=0.87,
            section="Section 4",
        )
        assert f.confidence == 0.87
        assert f.section == "Section 4"

    def test_risk_level_values(self):
        for level in ("critical", "high", "medium", "low", "acceptable"):
            f = Finding(**{**_FINDING_DEFAULTS, "risk_level": level})
            assert f.risk_level == level

    def test_confidence_default(self):
        f = Finding(**_FINDING_DEFAULTS)
        assert 0.0 <= f.confidence <= 1.0

    def test_section_defaults_none(self):
        f = Finding(**_FINDING_DEFAULTS)
        assert f.section is None
