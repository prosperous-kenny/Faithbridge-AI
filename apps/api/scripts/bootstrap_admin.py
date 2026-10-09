"""Create the one bootstrap operator account on an empty database.

The API's /auth/register deliberately refuses self-service admin or faith_leader
accounts (see docs/adr/IMPLEMENTATION_PLAN.md, "The one carried decision"), so a
fresh deployment needs exactly one operator-created admin. This script is that
operator step: it is idempotent, safe to re-run, and creates nothing else.

Usage (from apps/api, with DATABASE_URL pointing at the target database):

    $env:DATABASE_URL = "postgresql+asyncpg://..."
    python scripts/bootstrap_admin.py

Credentials come from BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD (and the
LEADER equivalents) when set; otherwise the emails default and random passwords
are generated and printed once.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionFactory, engine
from app.repositories import organizations as organizations_repo
from app.repositories import users as users_repo

ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@faithbridge.org")
LEADER_EMAIL = os.getenv("BOOTSTRAP_LEADER_EMAIL", "faith-leader@faithbridge.org")


def _password(env_key: str) -> tuple[str, bool]:
    supplied = os.getenv(env_key)
    if supplied:
        return supplied, False
    return secrets.token_urlsafe(12), True


async def main() -> None:
    admin_password, admin_generated = _password("BOOTSTRAP_ADMIN_PASSWORD")
    leader_password, leader_generated = _password("BOOTSTRAP_LEADER_PASSWORD")

    async with SessionFactory() as session:
        orgs = await organizations_repo.list_organizations(session, limit=1)
        if orgs:
            org = orgs[0]
        else:
            org = await organizations_repo.create(
                session, name="FaithBridge Demo Church", org_type="church"
            )

        created: list[str] = []
        existing: list[str] = []

        admin = await users_repo.get_by_email(session, ADMIN_EMAIL)
        if admin is None:
            admin = await users_repo.create(
                session,
                email=ADMIN_EMAIL,
                full_name="Bootstrap Admin",
                role="admin",
                password=admin_password,
            )
            created.append(f"admin {admin.email}")
        else:
            existing.append(f"admin {admin.email}")

        leader = await users_repo.get_by_email(session, LEADER_EMAIL)
        if leader is None:
            leader = await users_repo.create(
                session,
                email=LEADER_EMAIL,
                full_name="Bootstrap Faith Leader",
                role="faith_leader",
                password=leader_password,
                organization_id=org.id,
            )
            created.append(f"faith_leader {leader.email} in org {org.id}")
        else:
            existing.append(f"faith_leader {leader.email}")

        await session.commit()

    await engine.dispose()

    print(f"organization: {org.id} {org.name!r}")
    for line in created:
        print(f"created {line}")
    for line in existing:
        print(f"kept {line} (already present)")
    if admin_generated:
        print(f"admin password (generated, shown once): {admin_password}")
    if leader_generated:
        print(f"faith leader password (generated, shown once): {leader_password}")


if __name__ == "__main__":
    asyncio.run(main())
