"""Tests for risk_config.py numeric scoring."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from backend.app.risk_config import score_numeric, DEFAULT_RISK_CONFIG, get_config_for_jurisdiction  # noqa: E402


class TestPaymentTerms:
    def test_30_days_is_low(self):
        assert score_numeric("payment_terms", 30) == "low"

    def test_61_days_is_medium(self):
        assert score_numeric("payment_terms", 61) == "medium"

    def test_76_days_is_high(self):
        assert score_numeric("payment_terms", 76) == "high"

    def test_91_days_is_critical(self):
        assert score_numeric("payment_terms", 91) == "critical"

    def test_exactly_60_is_low(self):
        assert score_numeric("payment_terms", 60) == "low"

    def test_exactly_90_is_high(self):
        assert score_numeric("payment_terms", 90) == "high"


class TestRetainage:
    def test_5_percent_is_low(self):
        assert score_numeric("retainage", 5) == "low"

    def test_8_percent_is_medium(self):
        assert score_numeric("retainage", 8) == "medium"

    def test_12_percent_is_high(self):
        assert score_numeric("retainage", 12) == "high"

    def test_16_percent_is_critical(self):
        assert score_numeric("retainage", 16) == "critical"


class TestNoticePeriod:
    def test_3_days_is_critical(self):
        assert score_numeric("notice_period", 3) == "critical"

    def test_10_days_is_high(self):
        assert score_numeric("notice_period", 10) == "high"

    def test_21_days_is_low(self):
        assert score_numeric("notice_period", 21) == "low"


class TestCurePeriod:
    def test_30_days_is_low(self):
        assert score_numeric("cure_period", 30) == "low"

    def test_20_days_is_medium(self):
        assert score_numeric("cure_period", 20) == "medium"


def test_unknown_clause_type_returns_medium():
    assert score_numeric("unknown_clause", 999) == "medium"


def test_zero_value_returns_low_for_payment_terms():
    assert score_numeric("payment_terms", 0) == "low"


class TestJurisdictionOverrides:
    def test_de_stricter_payment_terms(self):
        de_config = get_config_for_jurisdiction("DE")
        assert score_numeric("payment_terms", 35, de_config) == "medium"

    def test_default_accepts_35_days(self):
        assert score_numeric("payment_terms", 35) == "low"

    def test_ca_more_lenient_payment_terms(self):
        ca_config = get_config_for_jurisdiction("CA")
        assert score_numeric("payment_terms", 61, ca_config) == "medium"

    def test_none_jurisdiction_returns_default(self):
        config = get_config_for_jurisdiction(None)
        assert "payment_terms" in config

    def test_unknown_jurisdiction_returns_default(self):
        config = get_config_for_jurisdiction("XX")
        assert config == DEFAULT_RISK_CONFIG

    def test_case_insensitive_jurisdiction(self):
        lower = get_config_for_jurisdiction("de")
        upper = get_config_for_jurisdiction("DE")
        assert lower == upper
