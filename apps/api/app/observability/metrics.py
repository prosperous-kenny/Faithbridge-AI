"""Prometheus metrics (Phase 5): request rate, latency histogram, and counters
per endpoint, plus a DB gauge refreshed on scrape.

The collector is a module-level singleton so every worker in the process shares
one registry. The ``/metrics`` route renders ``generate_latest()``; the
middleware that observes requests lives here too so ``main.py`` only wires it.
"""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "faithbridge_http_requests_total",
    "Total HTTP requests handled, by method and route",
    ["method", "route", "status"],
)
REQUEST_LATENCY = Histogram(
    "faithbridge_http_request_duration_seconds",
    "HTTP request latency in seconds, by method and route",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
DB_UP = Gauge(
    "faithbridge_db_up",
    "1 when a scrape-time database probe succeeds, else 0",
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Observe every request as it leaves: count by outcome, time by route.

    The route label comes from ``request.scope``; unmatched paths (404s, and
    anything that failed before routing) are bucketed under ``unknown`` so the
    metric never stars cardinality over raw paths.
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        route = getattr(request.scope.get("route"), "path", "unknown")
        REQUEST_COUNT.labels(
            method=request.method, route=route, status=str(response.status_code)
        ).inc()
        REQUEST_LATENCY.labels(method=request.method, route=route).observe(
            time.perf_counter() - start
        )
        return response


def metrics_text() -> tuple[bytes, str]:
    """The scrape payload for ``/metrics``.

    A lightweight DB probe is run on scrape (not on a timer) so the gauge
    reflects the health a monitor would see, and ``DB_UP`` is set even when no
    request has ever reached the database.
    """
    _probe_db()
    return generate_latest(), CONTENT_TYPE_LATEST


def _probe_db() -> None:
    try:
        from app.config import settings
        from app.db.session import engine
        from sqlalchemy import text

        if not settings.database_url:
            DB_UP.set(0.0)
            return
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        DB_UP.set(1.0)
    except Exception:  # noqa: BLE001 - a scrape must never 500
        DB_UP.set(0.0)


def metrics_response() -> Response:
    body, content_type = metrics_text()
    return Response(content=body, media_type=content_type)