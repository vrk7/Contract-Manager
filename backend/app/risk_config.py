"""
Structured risk configuration parsed from the playbook.

Provides numeric thresholds per clause type so _compare_with_playbook can
score against explicit ranges rather than hardcoded magic numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClauseRiskThresholds:
    low_max: Optional[float] = None
    medium_max: Optional[float] = None
    high_max: Optional[float] = None
    # values above high_max are critical
    unit: str = ""


DEFAULT_RISK_CONFIG: dict[str, ClauseRiskThresholds] = {
    "payment_terms": ClauseRiskThresholds(low_max=60, medium_max=75, high_max=90, unit="days"),
    "retainage": ClauseRiskThresholds(low_max=5, medium_max=10, high_max=15, unit="%"),
    "notice_period": ClauseRiskThresholds(low_max=None, medium_max=13, high_max=6, unit="days"),
    "termination_notice": ClauseRiskThresholds(low_max=None, medium_max=29, high_max=13, unit="days"),
    "cure_period": ClauseRiskThresholds(low_max=30, medium_max=14, high_max=7, unit="days"),
}


JURISDICTION_OVERRIDES: dict[str, dict[str, ClauseRiskThresholds]] = {
    "DE": {
        "payment_terms": ClauseRiskThresholds(low_max=30, medium_max=45, high_max=60, unit="days"),
        "retainage": ClauseRiskThresholds(low_max=3, medium_max=5, high_max=10, unit="%"),
    },
    "CA": {
        "payment_terms": ClauseRiskThresholds(low_max=45, medium_max=60, high_max=90, unit="days"),
    },
}


def get_config_for_jurisdiction(jurisdiction: str | None = None) -> dict[str, ClauseRiskThresholds]:
    """Return risk config merged with jurisdiction-specific overrides."""
    base = dict(DEFAULT_RISK_CONFIG)
    if jurisdiction and jurisdiction.upper() in JURISDICTION_OVERRIDES:
        base.update(JURISDICTION_OVERRIDES[jurisdiction.upper()])
    return base


def list_supported_clause_types() -> list[str]:
    """Return all clause types with explicit risk thresholds."""
    return sorted(DEFAULT_RISK_CONFIG.keys())


def score_numeric(clause_type: str, value: float, config: dict[str, ClauseRiskThresholds] | None = None) -> str:
    """
    Score a numeric clause value against the risk config.
    Returns risk_level string.
    """
    cfg = (config or DEFAULT_RISK_CONFIG).get(clause_type)
    if not cfg:
        return "medium"

    if clause_type in {"payment_terms", "retainage"}:
        if cfg.high_max is not None and value > cfg.high_max:
            return "critical"
        if cfg.medium_max is not None and value > cfg.medium_max:
            return "high"
        if cfg.low_max is not None and value > cfg.low_max:
            return "medium"
        return "low"
    elif clause_type in {"notice_period", "termination_notice", "cure_period"}:
        # Lower is worse for notice/cure periods
        if cfg.high_max is not None and value <= cfg.high_max:
            return "critical"
        if cfg.medium_max is not None and value <= cfg.medium_max:
            return "high"
        return "low"

    return "medium"
