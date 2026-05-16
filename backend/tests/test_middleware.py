"""Tests for RequestTimingMiddleware."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BYPASS_DB_FOR_TESTS", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import inspect
import typing

_orig_eval = typing.ForwardRef._evaluate  # type: ignore[attr-defined]
_sig = inspect.signature(_orig_eval)


def _patched(self, globalns, localns, *args, **kwargs):
    try:
        bound = _sig.bind(self, globalns, localns, *args, **kwargs)
    except TypeError:
        bound = _sig.bind_partial(self, globalns, localns, *args, **kwargs)
    if "recursive_guard" in _sig.parameters and "recursive_guard" not in bound.arguments:
        bound.arguments["recursive_guard"] = set()
    bound.apply_defaults()
    return _orig_eval(*bound.args, **bound.kwargs)


typing.ForwardRef._evaluate = _patched  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from backend.app.main import app  # noqa: E402

client = TestClient(app)


def test_health_returns_request_id_header():
    resp = client.get("/health")
    assert "x-request-id" in resp.headers


def test_custom_request_id_echoed_back():
    resp = client.get("/health", headers={"X-Request-ID": "my-trace-123"})
    assert resp.headers.get("x-request-id") == "my-trace-123"


def test_security_header_x_frame_options():
    resp = client.get("/health")
    assert resp.headers.get("x-frame-options") == "DENY"


def test_security_header_content_type_nosniff():
    resp = client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"


def test_security_header_csp_present():
    resp = client.get("/health")
    assert "content-security-policy" in resp.headers


def test_security_header_referrer_policy():
    resp = client.get("/health")
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
