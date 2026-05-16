"""Shared utilities for the Contract Analyzer backend."""
from __future__ import annotations

import hashlib
import re
import unicodedata


def normalize_text(text: str) -> str:
    """NFKC-normalize and strip leading/trailing whitespace."""
    return unicodedata.normalize("NFKC", text).strip()


def content_hash(text: str, length: int = 16) -> str:
    """Return a short SHA-256 hex digest of text for deduplication."""
    return hashlib.sha256(text.encode(), usedforsecurity=False).hexdigest()[:length]


def truncate_to_tokens(text: str, max_tokens: int = 100_000) -> str:
    """
    Rough token-budget guard: truncate text to approximately max_tokens tokens.
    Uses a 4-char-per-token heuristic (common for English prose).
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def extract_first_number(text: str) -> float | None:
    """Return the first integer or decimal found in text, or None."""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = normalize_text(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def redact_pii(text: str) -> str:
    """Replace common PII patterns with placeholder tokens for safe logging."""
    # Email addresses
    text = re.sub(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[EMAIL]", text)
    # US phone numbers
    text = re.sub(r"\b(\+?1[\s.-]?)?(\(?\d{3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}\b", "[PHONE]", text)
    # Social security numbers
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]", text)
    return text


def word_count(text: str) -> int:
    """Return the approximate word count of text."""
    return len(text.split())


def sentence_count(text: str) -> int:
    """Return the approximate sentence count of text."""
    return len(re.findall(r"[.!?]+", text)) or (1 if text.strip() else 0)


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))
