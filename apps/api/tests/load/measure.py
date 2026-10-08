"""Phase 5 load gate that runs with only the project's own dependencies.

The IMPLEMENTATION_PLAN gate is "dashboard p95 latency under 3 seconds under
load". k6 is optional on this machine, so this script reproduces the scenario
with the stdlib + httpx:

* seeds one organization with a realistic amount of Phase 1-5 data,
* boots the real API (``app.main:app`` via uvicorn) on a private port against
  the developer database (schema is checked against the Alembic head by the
  application's own lifespan),
* logs in as the organization's faith leader and hammers the four dashboard
  read paths from a small pool of concurrent workers,
* prints p95 per endpoint, fails with a non-zero exit code if any p95 (or the
  overall p95) reaches the 3 second threshold.

Run from apps/api:

    python tests/load/measure.py             # gate only
    python tests/load/measure.py --vus 80 --rounds 30 --no-gate

Seeded rows are best-effort cleaned up afterwards (named "LOAD GATE").
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import secrets
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

API_DIR = Path(__file__).resolve().parent.parent.parent
PYTHON = sys.executable
GATE_SECONDS = 3.0
PORT = 8137
BASE = f"http://127.0.0.1:{PORT}"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

ENDPOINTS = {
    "stats": "/api/v1/dashboard/stats",
    "community-insights": "/api/v1/dashboard/community-insights",
    "impact-report": "/api/v1/dashboard/impact-report",
    "export-pdf": "/api/v1/dashboard/impact-report/export?format=pdf",
}


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return ordered[index]


async def seed() -> dict:
    """Populate one organization with enough rows for realistic aggregates."""
    import datetime as _dt
    import importlib.util
    from datetime import UTC

    from app.db.session import SessionFactory
    from app.db.session import engine as _app_engine
    from app.repositories import users as users_repo

    _now = _dt.datetime.now(UTC).replace(tzinfo=None)
    _timedelta = _dt.timedelta

    spec = importlib.util.spec_from_file_location(
        "load_factories", API_DIR / "tests" / "factories.py"
    )
    factories = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(factories)

    email = f"load-gate-{secrets.token_hex(4)}@example.org"
    password = "load-horse-1"

    await cleanup()

    async with SessionFactory() as session:
        org = await factories.create_organization(session, name="LOAD GATE Church")
        await users_repo.create(
            session,
            email=email,
            full_name="Load Gate Leader",
            role="faith_leader",
            password=password,
            is_active=True,
            organization_id=org.id,
        )
        await factories.create_program(
            session, organization=org, name="LOAD GATE Program", category="housing"
        )
        for category in ("housing", "food", "education", "health"):
            for _ in range(25):
                await factories.create_assistance_request(
                    session,
                    organization=org,
                    category=category,
                    priority=random.choice(("low", "medium", "high", "critical")),
                )
        month_bucket = _now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for metric in (
            "families_supported",
            "education",
            "food_security",
            "healthcare",
            "employment",
        ):
            for offset in range(3):
                start = month_bucket - _timedelta(days=31 * offset)
                await factories.create_impact_rollup(
                    session,
                    organization=org,
                    metric=metric,
                    total=random.randint(1, 40),
                    period_start=start,
                    period_end=start + _timedelta(days=31),
                )
        await factories.create_impact_config(session, organization=org)
        await session.commit()
        await session.flush()

    await _app_engine.dispose()
    return {"email": email, "password": password}


async def cleanup() -> None:
    """Remove the LOAD GATE rows (best effort, dependency order).

    Uses its own engine: the app's global engine is bound to whatever event
    loop first imported it, and this script crosses loop boundaries.
    """
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.models import (
        AssistanceRequest,
        Beneficiary,
        DeletionRequest,
        Donation,
        ImpactEvent,
        ImpactRollup,
        Organization,
        OrgImpactConfig,
        Program,
        User,
    )

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        from app.config import settings

        url = settings.database_url

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                select(Organization.id).where(Organization.name == "LOAD GATE Church")
            )
            org_ids = [row[0] for row in result]
            if not org_ids:
                return
            for model in (
                DeletionRequest,
                Donation,
                ImpactRollup,
                ImpactEvent,
                AssistanceRequest,
                Beneficiary,
                Program,
                OrgImpactConfig,
            ):
                await conn.execute(
                    delete(model).where(model.organization_id.in_(org_ids))
                )
            await conn.execute(
                delete(User).where(User.organization_id.in_(org_ids))
            )
            await conn.execute(
                delete(Organization).where(Organization.id.in_(org_ids))
            )
            await conn.commit()
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup, never block the gate
        print(f"    cleanup failed: {exc}")
    finally:
        await engine.dispose()


async def wait_ready(semaphored_debug=False) -> bool:
    deadline = time.monotonic() + 30
    async with httpx.AsyncClient(base_url=BASE) as client:
        while time.monotonic() < deadline:
            try:
                res = await client.get("/health/ready")
                if res.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.3)
    return False


async def worker(
    client: httpx.AsyncClient,
    rounds: int,
    latencies: dict[str, list[float]],
    all_latencies: list[float],
) -> None:
    keys = list(ENDPOINTS)
    for _ in range(rounds):
        name = random.choice(keys)
        started = time.perf_counter()
        try:
            await client.get(ENDPOINTS[name])
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            latencies[name].append(elapsed)
        await asyncio.sleep(0.02)


async def run_load(token: str, vus: int, rounds: int) -> dict[str, list[float]]:
    latencies: dict[str, list[float]] = {name: [] for name in ENDPOINTS}
    all_latencies: list[float] = []
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=BASE, headers=headers) as client:
        coros = [worker(client, rounds, latencies, all_latencies) for _ in range(vus)]
        await asyncio.gather(*coros)
    return latencies


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vus", type=int, default=40)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--no-gate", action="store_true")
    args = parser.parse_args()

    print("[seed] creating LOAD GATE organization …")
    creds = asyncio.run(seed())

    server = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(API_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        if not asyncio.run(wait_ready()):
            print("API did not become ready; aborting", file=sys.stderr)
            return 3
        print(f"[ready] API up on {BASE}")

        async def login() -> str:
            async with httpx.AsyncClient(base_url=BASE) as client:
                res = await client.post(
                    "/api/v1/auth/login",
                    json={"email": creds["email"], "password": creds["password"]},
                )
                res.raise_for_status()
                return res.json()["access_token"]

        token = asyncio.run(login())
        print(f"[load] {args.vus} workers x {args.rounds} rounds …")
        latencies = asyncio.run(run_load(token, args.vus, args.rounds))

        print("\nendpoint                       p50      p95      max")
        overall = [v for vs in latencies.values() for v in vs]
        for name, values in latencies.items():
            print(
                f"  {name:<28} {statistics.median(values):7.1f} "
                f"{p95(values):7.1f} {max(values):7.1f}"
            )
        print(
            f"  {'overall':<28} {statistics.median(overall):7.1f} "
            f"{p95(overall):7.1f} {max(overall):7.1f}"
        )

        ok = True
        if not args.no_gate:
            for name, values in latencies.items():
                if p95(values) >= GATE_SECONDS * 1000:
                    print(f"GATE FAIL: {name} p95 {p95(values):.1f}ms >= 3000ms")
                    ok = False
            if p95(overall) >= GATE_SECONDS * 1000:
                print(f"GATE FAIL: overall p95 {p95(overall):.1f}ms >= 3000ms")
                ok = False
            if ok:
                print(f"\nGATE PASS: all endpoints p95 < {GATE_SECONDS * 1000:.0f}ms")
        return 0 if ok else 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        print("[cleanup] removing LOAD GATE rows …")
        asyncio.run(cleanup())


if __name__ == "__main__":
    os.environ.setdefault("FAITHBRIDGE_ENV", "development")
    raise SystemExit(main())