"""Unit tests for llm.py — structured output parsing."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.llm import _parse_llm_output  # noqa: E402


def test_parse_valid_json():
    raw = '{"risk_level": "high", "deviation_summary": "Above standard", "recommendation": "Negotiate down.", "confidence": 0.8}'
    result = _parse_llm_output(raw)
    assert result.risk_level == "high"
    assert result.deviation_summary == "Above standard"
    assert result.recommendation == "Negotiate down."
    assert result.confidence == 0.8


def test_parse_json_with_surrounding_text():
    raw = 'Here is the analysis:\n{"risk_level": "critical", "deviation_summary": "Broad indemnity", "recommendation": "Limit scope.", "confidence": 0.9}\nEnd of analysis.'
    result = _parse_llm_output(raw)
    assert result.risk_level == "critical"
    assert result.recommendation == "Limit scope."


def test_parse_invalid_json_returns_fallback():
    raw = "This is not JSON at all."
    result = _parse_llm_output(raw)
    assert result.risk_level == "medium"
    assert result.recommendation == raw.strip()


def test_parse_partial_json_uses_defaults():
    raw = '{"risk_level": "low"}'
    result = _parse_llm_output(raw)
    assert result.risk_level == "low"
    assert result.recommendation == ""
    assert result.deviation_summary == ""


def test_parse_empty_string_returns_fallback():
    result = _parse_llm_output("")
    assert result.risk_level == "medium"


def test_parse_unknown_risk_level_uses_default():
    raw = '{"risk_level": "unknown", "recommendation": "Review carefully."}'
    result = _parse_llm_output(raw)
    assert result.risk_level == "unknown"


def test_confidence_clamped_to_valid_range():
    raw = '{"risk_level": "medium", "confidence": 0.75}'
    result = _parse_llm_output(raw)
    assert 0.0 <= result.confidence <= 1.0
