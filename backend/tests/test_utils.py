"""Unit tests for shared utils."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.utils import (  # noqa: E402
    clamp,
    content_hash,
    extract_first_number,
    normalize_text,
    redact_pii,
    sentence_count,
    slugify,
    truncate_to_tokens,
    word_count,
)


class TestNormalizeText:
    def test_strips_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_nfkc_normalizes_ligature(self):
        assert normalize_text("ﬁrst") == "first"

    def test_empty_string(self):
        assert normalize_text("") == ""


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("same") == content_hash("same")

    def test_different_inputs_differ(self):
        assert content_hash("a") != content_hash("b")

    def test_length_respected(self):
        assert len(content_hash("text", length=8)) == 8

    def test_default_length_16(self):
        assert len(content_hash("text")) == 16


class TestTruncateToTokens:
    def test_short_text_unchanged(self):
        text = "Short text."
        assert truncate_to_tokens(text, max_tokens=100) == text

    def test_long_text_truncated(self):
        text = "A" * 1000
        result = truncate_to_tokens(text, max_tokens=10)
        assert len(result) == 40

    def test_exact_limit_unchanged(self):
        text = "A" * 40
        assert truncate_to_tokens(text, max_tokens=10) == text


class TestExtractFirstNumber:
    def test_integer(self):
        assert extract_first_number("payment 30 days") == 30.0

    def test_decimal(self):
        assert extract_first_number("retainage 5.5%") == 5.5

    def test_no_number_returns_none(self):
        assert extract_first_number("no numbers here") is None

    def test_takes_first_number(self):
        assert extract_first_number("30 or 45 days") == 30.0


class TestSlugify:
    def test_spaces_become_hyphens(self):
        assert slugify("Payment Terms") == "payment-terms"

    def test_special_chars_removed(self):
        assert slugify("Hello, World!") == "hello-world"

    def test_leading_trailing_hyphens_stripped(self):
        result = slugify("  test  ")
        assert not result.startswith("-")
        assert not result.endswith("-")


class TestRedactPii:
    def test_redacts_email(self):
        assert "[EMAIL]" in redact_pii("Contact us at user@example.com for details.")

    def test_redacts_ssn(self):
        assert "[SSN]" in redact_pii("My SSN is 123-45-6789.")

    def test_no_pii_unchanged(self):
        text = "Payment terms are net 30 days."
        assert redact_pii(text) == text

    def test_multiple_emails_all_redacted(self):
        result = redact_pii("From: a@b.com To: c@d.com")
        assert "a@b.com" not in result
        assert "c@d.com" not in result


class TestWordCount:
    def test_basic_sentence(self):
        assert word_count("hello world foo") == 3

    def test_empty_string(self):
        assert word_count("") == 0

    def test_single_word(self):
        assert word_count("hello") == 1


class TestSentenceCount:
    def test_multiple_sentences(self):
        assert sentence_count("Hello. World. Foo.") == 3

    def test_empty_string_zero(self):
        assert sentence_count("") == 0

    def test_no_punctuation_counts_as_one(self):
        assert sentence_count("no punctuation here") == 1


class TestClamp:
    def test_within_range(self):
        assert clamp(0.5, 0.0, 1.0) == 0.5

    def test_below_lo(self):
        assert clamp(-1.0, 0.0, 1.0) == 0.0

    def test_above_hi(self):
        assert clamp(2.0, 0.0, 1.0) == 1.0

    def test_at_boundary(self):
        assert clamp(0.0, 0.0, 1.0) == 0.0
        assert clamp(1.0, 0.0, 1.0) == 1.0
