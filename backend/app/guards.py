from __future__ import annotations

import re
from typing import Iterable

from .schemas import GuardrailWarning

INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore (the )?(previous|above) instructions", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"pretend to be", re.IGNORECASE),
    re.compile(r"exfiltrate", re.IGNORECASE),
    re.compile(r"unrelated task", re.IGNORECASE),
]


def filter_malicious_segments(text: str) -> tuple[str, list[GuardrailWarning]]:
    warnings: list[GuardrailWarning] = []
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            warnings.append(
                GuardrailWarning(
                    type="content_filter",
                    message="Detected potential prompt injection content; sanitized input.",
                    triggered_by=pattern.pattern,
                )
            )
            sanitized = pattern.sub("[filtered]", sanitized)
    return sanitized, warnings


def ensure_retrieval_guardrails(findings: Iterable[dict]) -> list[GuardrailWarning]:
    warnings: list[GuardrailWarning] = []
    for finding in findings:
        if not finding.get("source_text"):
            warnings.append(
                GuardrailWarning(
                    type="validation",
                    message="Dropped finding without contract source text.",
                    triggered_by=finding.get("clause_type", "unknown"),
                )
            )
        if not finding.get("retrieved_chunks"):
            warnings.append(
                GuardrailWarning(
                    type="validation",
                    message="Dropped finding without retrieved playbook chunks.",
                    triggered_by=finding.get("clause_type", "unknown"),
                )
            )
    return warnings
