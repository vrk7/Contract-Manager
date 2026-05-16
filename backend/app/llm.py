from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import anthropic
import structlog

from .config import get_settings
from .schemas import LLMFindingOutput, LLMObligationOutput, LLMSummaryOutput

logger = structlog.get_logger(__name__)
settings = get_settings()

SYSTEM_PROMPT = (
    "You are a construction contract risk advisor. "
    "Analyze contract clauses against playbook standards and identify risks. "
    "Always cite the specific playbook standard you are comparing against. "
    "Think step-by-step before deciding on a risk level."
)

# ── Tool definitions sent to Claude for forced structured output ──────────────

_RISK_TOOL: dict[str, Any] = {
    "name": "record_risk_finding",
    "description": (
        "Record a structured risk finding for a contract clause after comparing it "
        "against the playbook standard. Think through: (1) what risk this clause poses "
        "to the contractor, (2) how it deviates from the standard, (3) what concrete "
        "negotiation action would fix it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "risk_level": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low", "acceptable", "unknown"],
                "description": "Overall risk level for this clause.",
            },
            "deviation_summary": {
                "type": "string",
                "description": "One sentence describing how the clause deviates from the playbook standard.",
            },
            "recommendation": {
                "type": "string",
                "description": "2-3 sentence concrete negotiation recommendation to bring the clause in line.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in the assessment, 0.0 to 1.0.",
            },
        },
        "required": ["risk_level", "deviation_summary", "recommendation", "confidence"],
    },
}

_SUMMARY_TOOL: dict[str, Any] = {
    "name": "record_clause_summary",
    "description": "Record a plain-language summary of a contract clause for a project manager.",
    "input_schema": {
        "type": "object",
        "properties": {
            "plain_language": {
                "type": "string",
                "description": "1-2 sentence plain-language explanation of what this clause means.",
            },
            "key_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key values or terms from the clause (dates, amounts, thresholds).",
            },
            "risk_flag": {
                "type": "boolean",
                "description": "True if this clause poses a notable risk worth flagging.",
            },
        },
        "required": ["plain_language", "key_terms", "risk_flag"],
    },
}

_OBLIGATION_TOOL: dict[str, Any] = {
    "name": "record_obligations",
    "description": "Record the specific contractual obligations this clause creates for the contractor.",
    "input_schema": {
        "type": "object",
        "properties": {
            "obligations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of concrete, action-oriented obligations.",
            },
            "party": {
                "type": "string",
                "enum": ["contractor", "owner", "both"],
                "description": "Which party bears the primary obligation.",
            },
            "deadline": {
                "type": "string",
                "description": "Any deadline or time constraint mentioned, or null.",
            },
            "consequence": {
                "type": "string",
                "description": "Consequence of non-compliance, or null if not specified.",
            },
        },
        "required": ["obligations", "party"],
    },
}


@dataclass
class LLMUsage:
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost(self) -> float:
        return (
            self.input_tokens * settings.cost_per_input_token
            + self.output_tokens * settings.cost_per_output_token
        )


class AnthropicClient:
    def __init__(self) -> None:
        self.api_key = settings.anthropic_api_key
        self.model = settings.anthropic_model
        self.max_retries = settings.llm_max_retries
        self.client: Optional[anthropic.AsyncAnthropic] = None
        if self.api_key:
            self.client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=self.max_retries,
            )
        else:
            logger.warning("anthropic_key_missing", detail="LLM calls will use heuristic fallback")

    async def _call_with_tool(
        self,
        prompt: str,
        tool: dict[str, Any],
        max_tokens: int = 512,
        playbook_context: str | None = None,
    ) -> tuple[dict[str, Any], LLMUsage]:
        """
        Call Claude with a single forced tool and return its input dict.
        Falls back to an empty dict on missing API key.
        """
        if not self.client:
            approx = len(prompt) // 4
            return {}, LLMUsage(approx, 0)

        user_blocks: list[Any] = []
        if playbook_context:
            user_blocks.append({
                "type": "text",
                "text": f"Playbook reference:\n{playbook_context}",
                "cache_control": {"type": "ephemeral"},
            })
        user_blocks.append({"type": "text", "text": prompt})

        t0 = time.monotonic()
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": user_blocks}],
            )
        except anthropic.AuthenticationError as exc:
            logger.error("anthropic_auth_error", model=self.model, message=str(exc))
            return {}, LLMUsage(len(prompt) // 4, 0)
        except anthropic.APIStatusError as exc:
            logger.error("anthropic_api_error", status_code=exc.status_code, message=exc.message)
            raise
        except anthropic.APIConnectionError as exc:
            logger.error("anthropic_connection_error", error=str(exc))
            raise

        duration_ms = int((time.monotonic() - t0) * 1000)
        usage = LLMUsage(message.usage.input_tokens or 0, message.usage.output_tokens or 0)
        logger.info(
            "llm_call_complete",
            model=self.model,
            tool=tool["name"],
            duration_ms=duration_ms,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=round(usage.estimated_cost, 6),
        )

        for block in message.content:
            if block.type == "tool_use":
                return block.input, usage  # type: ignore[attr-defined]
        return {}, usage

    async def analyze_risk(
        self,
        prompt: str,
        max_tokens: int = 512,
        playbook_context: str | None = None,
    ) -> tuple[LLMFindingOutput, LLMUsage]:
        """Analyze a clause for risk level, deviation, and recommendation via tool_use."""
        raw, usage = await self._call_with_tool(prompt, _RISK_TOOL, max_tokens, playbook_context)
        if not raw:
            return LLMFindingOutput(), usage
        try:
            return LLMFindingOutput(**raw), usage
        except Exception:
            logger.warning("llm_risk_parse_fallback", raw=str(raw)[:200])
            return LLMFindingOutput(), usage

    async def summarize_clause(
        self,
        prompt: str,
        max_tokens: int = 256,
        playbook_context: str | None = None,
    ) -> tuple[LLMSummaryOutput, LLMUsage]:
        """Produce a plain-language summary of a clause via tool_use."""
        raw, usage = await self._call_with_tool(prompt, _SUMMARY_TOOL, max_tokens, playbook_context)
        if not raw:
            return LLMSummaryOutput(), usage
        try:
            return LLMSummaryOutput(**raw), usage
        except Exception:
            logger.warning("llm_summary_parse_fallback", raw=str(raw)[:200])
            return LLMSummaryOutput(), usage

    async def extract_obligations(
        self,
        prompt: str,
        max_tokens: int = 384,
        playbook_context: str | None = None,
    ) -> tuple[LLMObligationOutput, LLMUsage]:
        """Extract contractor obligations from a clause via tool_use."""
        raw, usage = await self._call_with_tool(prompt, _OBLIGATION_TOOL, max_tokens, playbook_context)
        if not raw:
            return LLMObligationOutput(), usage
        try:
            return LLMObligationOutput(**raw), usage
        except Exception:
            logger.warning("llm_obligation_parse_fallback", raw=str(raw)[:200])
            return LLMObligationOutput(), usage

    # ── Legacy compat — kept for any callers not yet migrated ─────────────────

    async def complete_structured(
        self,
        prompt: str,
        max_tokens: int = 512,
        playbook_context: str | None = None,
    ) -> tuple[LLMFindingOutput, LLMUsage]:
        return await self.analyze_risk(prompt, max_tokens, playbook_context)
