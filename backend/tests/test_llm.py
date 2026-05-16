"""Unit tests for llm.py — structured output schemas and client fallback."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.schemas import LLMFindingOutput, LLMObligationOutput, LLMSummaryOutput  # noqa: E402


# ── LLMFindingOutput ─────────────────────────────────────────────────────────

def test_finding_output_defaults():
    out = LLMFindingOutput()
    assert out.risk_level == "medium"
    assert out.deviation_summary == ""
    assert out.recommendation == ""
    assert out.confidence == 0.5


def test_finding_output_full():
    out = LLMFindingOutput(
        risk_level="high",
        deviation_summary="Above standard",
        recommendation="Negotiate down.",
        confidence=0.8,
    )
    assert out.risk_level == "high"
    assert out.deviation_summary == "Above standard"
    assert out.recommendation == "Negotiate down."
    assert out.confidence == 0.8


def test_finding_output_confidence_bounds():
    out = LLMFindingOutput(confidence=0.0)
    assert out.confidence == 0.0
    out2 = LLMFindingOutput(confidence=1.0)
    assert out2.confidence == 1.0


def test_finding_output_unknown_risk():
    out = LLMFindingOutput(risk_level="unknown")
    assert out.risk_level == "unknown"


# ── LLMSummaryOutput ─────────────────────────────────────────────────────────

def test_summary_output_defaults():
    out = LLMSummaryOutput()
    assert out.plain_language == ""
    assert out.key_terms == []
    assert out.risk_flag is False


def test_summary_output_full():
    out = LLMSummaryOutput(
        plain_language="Payment is due in 45 days.",
        key_terms=["45 days", "invoice"],
        risk_flag=True,
    )
    assert out.plain_language == "Payment is due in 45 days."
    assert "45 days" in out.key_terms
    assert out.risk_flag is True


# ── LLMObligationOutput ───────────────────────────────────────────────────────

def test_obligation_output_defaults():
    out = LLMObligationOutput()
    assert out.obligations == []
    assert out.party == "contractor"
    assert out.deadline is None
    assert out.consequence is None


def test_obligation_output_full():
    out = LLMObligationOutput(
        obligations=["Submit invoice within 30 days", "Provide lien waiver"],
        party="contractor",
        deadline="30 days after completion",
        consequence="Forfeiture of payment right",
    )
    assert len(out.obligations) == 2
    assert out.deadline == "30 days after completion"
    assert out.consequence == "Forfeiture of payment right"


# ── AnthropicClient fallback (no API key) ────────────────────────────────────

def test_client_returns_defaults_without_api_key():
    """AnthropicClient with no key should not raise — fallback returns empty dicts."""
    import asyncio
    from backend.app.llm import AnthropicClient

    client = AnthropicClient()
    assert client.client is None  # no key → no real client

    async def _run():
        out, usage = await client.analyze_risk("test prompt")
        assert isinstance(out, LLMFindingOutput)
        assert usage.input_tokens >= 0

    asyncio.run(_run())
