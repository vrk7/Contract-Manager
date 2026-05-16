"""Reusable ASGI middleware helpers."""
from __future__ import annotations

import time
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

SLOW_REQUEST_THRESHOLD_MS = 2000


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log request method, path, status, and duration for every HTTP call."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        t0 = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - t0) * 1000)
        log_fn = logger.warning if duration_ms >= SLOW_REQUEST_THRESHOLD_MS else logger.info
        log_fn(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            slow=duration_ms >= SLOW_REQUEST_THRESHOLD_MS,
        )
        return response
