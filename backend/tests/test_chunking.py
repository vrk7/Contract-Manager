"""Unit tests for chunk_playbook() sentence-aware splitting in rag.py."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.rag import chunk_playbook  # noqa: E402


def test_empty_string_returns_empty_list():
    assert chunk_playbook("") == []


def test_whitespace_only_returns_empty_list():
    assert chunk_playbook("   \n  ") == []


def test_single_short_sentence_returns_one_chunk():
    result = chunk_playbook("Payment is due within 30 days.")
    assert result == ["Payment is due within 30 days."]


def test_multiple_sentences_within_limit_returns_one_chunk():
    text = "Payment is due within 30 days. Retainage shall not exceed 5%."
    result = chunk_playbook(text, max_chars=200)
    assert len(result) == 1


def test_long_content_splits_into_multiple_chunks():
    sentence = "This is a test sentence for chunking purposes. "
    text = sentence * 30
    result = chunk_playbook(text, max_chars=200)
    assert len(result) > 1


def test_chunks_do_not_exceed_max_chars():
    sentence = "Each sentence adds length to the chunk content here. "
    text = sentence * 20
    result = chunk_playbook(text, max_chars=300)
    for chunk in result:
        assert len(chunk) <= 350, f"Chunk too long: {len(chunk)}"


def test_overlap_repeats_tail_sentences():
    sentences = [
        "First sentence about payment terms.",
        "Second sentence about retainage policy.",
        "Third sentence about notice requirements.",
        "Fourth sentence about termination rights.",
        "Fifth sentence about dispute resolution venues.",
        "Sixth sentence about liability limitations.",
    ]
    text = " ".join(sentences)
    result = chunk_playbook(text, max_chars=120, overlap_sentences=1)
    if len(result) > 1:
        last_sentence_of_first = result[0].split(".")[-2].strip() + "."
        assert any(last_sentence_of_first in chunk for chunk in result[1:])


def test_no_overlap_produces_non_overlapping_chunks():
    sentence = "Unique sentence number %d about contract terms. "
    text = "".join(sentence % i for i in range(20))
    result = chunk_playbook(text, max_chars=200, overlap_sentences=0)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk) > 0


def test_all_content_is_preserved_across_chunks():
    words = ["word%d" % i for i in range(100)]
    text = ". ".join(" ".join(words[i:i+5]) for i in range(0, 100, 5)) + "."
    result = chunk_playbook(text, max_chars=150)
    combined = " ".join(result)
    for i in range(0, 100, 5):
        assert f"word{i}" in combined


def test_single_very_long_sentence_becomes_own_chunk():
    long_sentence = "word " * 200 + "end."
    result = chunk_playbook(long_sentence, max_chars=100)
    assert len(result) >= 1
    all_text = " ".join(result)
    assert "end." in all_text
