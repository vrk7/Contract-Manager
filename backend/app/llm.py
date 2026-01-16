from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import anthropic

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


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
            self.client = anthropic.AsyncAnthropic(api_key=self.api_key)

    async def complete(self, prompt: str, max_tokens: int = 512) -> tuple[str, LLMUsage]:
        """
        Run a lightweight Claude completion. If no API key is configured,
        return a deterministic heuristic response to keep tests offline.
        """
        if not self.client:
            faux_output = "Heuristic analysis: compare extracted clauses to playbook references."
            approx_input_tokens = len(prompt) // 4
            approx_output_tokens = len(faux_output) // 4
            usage = LLMUsage(approx_input_tokens, approx_output_tokens)
            return faux_output, usage

        message = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        output_text = "".join([block.text for block in message.content if hasattr(block, "text")])
        usage = LLMUsage(
            message.usage.input_tokens or 0,
            message.usage.output_tokens or 0,
        )
        return output_text, usage
