"""Sentry initialisation (Phase 5).

Enabled only when ``SENTRY_DSN`` is configured; without it the module is a
no-op so local and test processes never contact Sentry or pay its import cost
at runtime.
"""

from __future__ import annotations

from app.config import settings


def init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )