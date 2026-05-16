"""Unit tests for analysis result cache."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.app.cache import AnalysisCache  # noqa: E402


def test_get_returns_none_on_miss():
    cache = AnalysisCache()
    assert cache.get("nonexistent") is None


def test_set_and_get_round_trips():
    cache = AnalysisCache()
    cache.set("k1", {"result": "ok"})
    assert cache.get("k1") == {"result": "ok"}


def test_make_key_is_deterministic():
    k1 = AnalysisCache.make_key("contract text", "v1", "risks")
    k2 = AnalysisCache.make_key("contract text", "v1", "risks")
    assert k1 == k2


def test_different_inputs_produce_different_keys():
    k1 = AnalysisCache.make_key("contract A", "v1", "risks")
    k2 = AnalysisCache.make_key("contract B", "v1", "risks")
    assert k1 != k2


def test_different_analysis_types_produce_different_keys():
    k1 = AnalysisCache.make_key("same text", "v1", "risks")
    k2 = AnalysisCache.make_key("same text", "v1", "summary")
    assert k1 != k2


def test_eviction_when_max_entries_exceeded():
    cache = AnalysisCache(max_entries=3)
    for i in range(4):
        cache.set(f"key{i}", i)
    assert cache.get("key0") is None
    assert cache.get("key3") == 3


def test_clear_removes_all_entries():
    cache = AnalysisCache()
    cache.set("k1", 1)
    cache.set("k2", 2)
    cache.clear()
    assert cache.get("k1") is None
    assert cache.get("k2") is None


def test_overwrite_existing_key():
    cache = AnalysisCache()
    cache.set("k1", "first")
    cache.set("k1", "second")
    assert cache.get("k1") == "second"


def test_delete_removes_entry():
    cache = AnalysisCache()
    cache.set("k1", "val")
    assert cache.delete("k1") is True
    assert cache.get("k1") is None


def test_delete_missing_key_returns_false():
    cache = AnalysisCache()
    assert cache.delete("nonexistent") is False


def test_size_tracks_entries():
    cache = AnalysisCache()
    assert cache.size() == 0
    cache.set("k1", 1)
    cache.set("k2", 2)
    assert cache.size() == 2


def test_size_after_delete():
    cache = AnalysisCache()
    cache.set("k1", 1)
    cache.set("k2", 2)
    cache.delete("k1")
    assert cache.size() == 1


def test_size_after_clear():
    cache = AnalysisCache()
    cache.set("k1", 1)
    cache.clear()
    assert cache.size() == 0
