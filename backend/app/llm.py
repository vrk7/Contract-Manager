from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import anthropic

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = (
    "You are a construction contract risk advisor. "
    "Analyze contract clauses against playbook standards and identify risks. "
    "Always cite the specific playbook standard you are comparing against."
)

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
        self.client: Optional[anthropic.AsyncAnthropic] = None
        if self.api_key:
            self.client = anthropic.AsyncAnthropic(api_key=self.api_key, timeout=60.0)

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
            usage = LLMUsage(approx_input_tokens, approx_output_tokens)
            return faux_output, usage

        user_blocks: list[dict] = []
        if playbook_context:
            user_blocks.append({"type": "text", "text": f"Playbook reference:\n{playbook_context}"})
        user_blocks.append({"type": "text", "text": prompt})

        message = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_blocks}],
        )
        output_text = "".join([block.text for block in message.content if hasattr(block, "text")])
        usage = LLMUsage(
            message.usage.input_tokens or 0,
            message.usage.output_tokens or 0,
        )
        return output_text, usage
