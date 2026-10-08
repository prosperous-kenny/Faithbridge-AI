"""Celery wiring for a deployed broker topology (Phase 2, documented unverified).

This machine has no Redis, so the broker path in this module has never been
executed. It is the declared *target* topology: when resources exist, install
Celery, start Redis, set ``CELERY_BROKER_URL``, and the tasks in ``tasks.py``
run on a worker with no code changes.

Safely importable without Celery: returning ``None`` is the signal that local
and test environments use the in-process ``BackgroundTasks`` dispatch instead.
A deployed environment that sets ``CELERY_BROKER_URL`` degrades to nothing:
either Celery is installed and the app starts, or startup raises.
"""

from __future__ import annotations

import os


def make_celery():
    """Build the Celery app only when a broker is configured and installed."""
    broker = os.getenv("CELERY_BROKER_URL", "").strip()
    if not broker:
        return None
    try:
        from celery import Celery  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on environment deps
        raise RuntimeError(
            "CELERY_BROKER_URL is set but celery is not installed; either add "
            "the dependency or unset the broker to use in-process dispatch."
        ) from exc

    app = Celery("faithbridge", broker=broker, include=["app.workers.tasks"])
    app.conf.task_routes = {"app.workers.tasks.*": {"queue": "assistance"}}
    app.conf.broker_connection_retry_on_startup = True
    return app


celery_app = make_celery()