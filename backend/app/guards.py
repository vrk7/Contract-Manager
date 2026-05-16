from __future__ import annotations

import re
import unicodedata
from typing import Iterable

import structlog

from .schemas import GuardrailWarning

logger = structlog.get_logger(__name__)

INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore (the )?(previous|above) instructions", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"pretend to be", re.IGNORECASE),
    re.compile(r"exfiltrate", re.IGNORECASE),
    re.compile(r"unrelated task", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN mode", re.IGNORECASE),
    re.compile(r"act as (an? )?(unrestricted|unfiltered|evil|malicious)", re.IGNORECASE),
    re.compile(r"disregard (all )?(previous|prior|above)", re.IGNORECASE),
    re.compile(r"override (your )?(safety|guidelines|instructions)", re.IGNORECASE),
]

_ZERO_WIDTH_RE = re.compile(r"[​-‏‪-‮⁠-⁯﻿]")

MAX_INPUT_CHARS = 5_000_000


def filter_malicious_segments(text: str) -> tuple[str, list[GuardrailWarning]]:
    warnings: list[GuardrailWarning] = []
    sanitized = text

    if len(sanitized) > MAX_INPUT_CHARS:
        warnings.append(
            GuardrailWarning(
                type="input_too_large",
                message=f"Input truncated from {len(sanitized)} to {MAX_INPUT_CHARS} characters.",
                triggered_by="size_limit",
            )
        )
        sanitized = sanitized[:MAX_INPUT_CHARS]

    if _ZERO_WIDTH_RE.search(sanitized):
        logger.warning("zero_width_chars_detected")
        warnings.append(
            GuardrailWarning(
                type="content_filter",
                message="Zero-width or invisible characters detected and removed.",
                triggered_by="zero_width_chars",
            )
        )
        sanitized = _ZERO_WIDTH_RE.sub("", sanitized)

    sanitized = unicodedata.normalize("NFKC", sanitized)

    for pattern in INJECTION_PATTERNS:
        if pattern.search(sanitized):
            logger.warning("injection_pattern_detected", pattern=pattern.pattern)
            warnings.append(
                GuardrailWarning(
                    type="content_filter",
                    message="Detected potential prompt injection content; sanitized input.",
                    triggered_by=pattern.pattern,
                )
            )
            sanitized = pattern.sub("[filtered]", sanitized)
    return sanitized, warnings


def score_text_complexity(text: str) -> dict:
    """Return basic readability metrics for a contract text segment."""
    words = text.split()
    sentences = max(len(re.findall(r"[.!?]+", text)), 1)
    avg_words_per_sentence = len(words) / sentences if sentences else 0
    long_words = sum(1 for w in words if len(w) > 8)
    return {
        "word_count": len(words),
        "sentence_count": sentences,
        "avg_words_per_sentence": round(avg_words_per_sentence, 1),
        "long_word_ratio": round(long_words / max(len(words), 1), 3),
    }


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
