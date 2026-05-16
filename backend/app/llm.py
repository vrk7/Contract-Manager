from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

import anthropic
import structlog

from .config import get_settings
from .schemas import LLMFindingOutput

logger = structlog.get_logger(__name__)
settings = get_settings()

SYSTEM_PROMPT = (
    "You are a construction contract risk advisor. "
    "Analyze contract clauses against playbook standards and identify risks. "
    "Always cite the specific playbook standard you are comparing against. "
    "When asked for structured output, respond ONLY with valid JSON matching the requested schema."
)

STRUCTURED_OUTPUT_SCHEMA = """{
  "risk_level": "<critical|high|medium|low|acceptable|unknown>",
  "deviation_summary": "<one sentence describing the deviation>",
  "recommendation": "<2-3 sentence concrete negotiation recommendation>",
  "confidence": <0.0-1.0>
}"""

COT_INSTRUCTIONS = (
    "\n\nThink step-by-step:\n"
    "1. Identify the specific risk this clause poses to the contractor.\n"
    "2. Compare the extracted value against the playbook standard.\n"
    "3. State a concrete negotiation action to bring it in line with the standard."
)


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

    async def complete(
        self,
        prompt: str,
        max_tokens: int = 512,
        playbook_context: str | None = None,
    ) -> tuple[str, LLMUsage]:
        """
        Run a Claude completion with an optional cached playbook context block.
        Falls back to a deterministic heuristic response when no API key is set.
        """
        if not self.client:
            faux_output = "Heuristic analysis: compare extracted clauses to playbook references."
            approx_input_tokens = len(prompt) // 4
            approx_output_tokens = len(faux_output) // 4
            return faux_output, LLMUsage(approx_input_tokens, approx_output_tokens)

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
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_blocks}],
            )
        except anthropic.APIStatusError as exc:
            logger.error("anthropic_api_error", status_code=exc.status_code, model=self.model, message=exc.message)
            raise
        except anthropic.APIConnectionError as exc:
            logger.error("anthropic_connection_error", model=self.model, error=str(exc))
            raise

        duration_ms = int((time.monotonic() - t0) * 1000)
        output_text = "".join([block.text for block in message.content if hasattr(block, "text")])
        usage = LLMUsage(
            message.usage.input_tokens or 0,
            message.usage.output_tokens or 0,
        )
        logger.info(
            "llm_call_complete",
            model=self.model,
            duration_ms=duration_ms,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=round(usage.estimated_cost, 6),
        )
        return output_text, usage

    async def complete_structured(
        self,
        prompt: str,
        max_tokens: int = 512,
        playbook_context: str | None = None,
    ) -> tuple[LLMFindingOutput, LLMUsage]:
        """
        Run a Claude completion and parse the response as LLMFindingOutput JSON.
        Falls back to a default LLMFindingOutput on parse failure.
        """
        structured_prompt = (
            f"{prompt}\n\n"
            f"Respond ONLY with JSON matching this schema:\n{STRUCTURED_OUTPUT_SCHEMA}"
        )
        raw, usage = await self.complete(structured_prompt, max_tokens=max_tokens, playbook_context=playbook_context)
        return _parse_llm_output(raw), usage


def _parse_llm_output(raw: str) -> LLMFindingOutput:
    """Parse raw LLM text as LLMFindingOutput, with graceful fallback."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            return LLMFindingOutput(**data)
    except Exception:
        pass
    return LLMFindingOutput(recommendation=raw.strip())
