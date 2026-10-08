"""Phase 3 donor preferences: one row per donor, full-replacement upsert.

The preference row is what the matching endpoint falls back on when the donor
does not pass inline overrides (PRD Use Case 2): the row is always scoped to
the authenticated donor id and never readable or writable for another user.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import DonorPreference
from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"


async def test_preferences_are_null_before_first_put(client, make_user, login):
    donor = await make_user("donor")
    response = client.get(f"{API}/donors/preferences/", headers=login(donor))
    assert response.status_code == 200, response.text
    assert response.json() is None


async def test_put_creates_and_returns_preferences(client, make_user, login):
    donor = await make_user("donor")
    response = client.put(
        f"{API}/donors/preferences/",
        headers=login(donor),
        json={"causes": ["housing", "food"], "budget": 1000.0, "location": "Lagos"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["causes"] == ["housing", "food"]
    assert body["budget"] == 1000.0
    assert body["location"] == "Lagos"
    assert body["donor_id"] == donor.id

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(DonorPreference).where(DonorPreference.donor_id == donor.id)
            )
        ).scalars().all()
        assert len(rows) == 1, "exactly one preference row per donor"


async def test_put_replaces_instead_of_accumulating(client, make_user, login):
    donor = await make_user("donor")
    headers = login(donor)
    first = client.put(
        f"{API}/donors/preferences/",
        headers=headers,
        json={"causes": ["housing"]},
    )
    assert first.status_code == 200
    row_id = first.json()["id"]

    second = client.put(
        f"{API}/donors/preferences/",
        headers=headers,
        json={"causes": ["food", "medical"], "budget": 1500, "location": "Accra"},
    )
    assert second.status_code == 200
    assert second.json()["id"] == row_id, "upsert keeps the same row"
    assert second.json()["causes"] == ["food", "medical"]

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(DonorPreference).where(DonorPreference.donor_id == donor.id)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].causes == ["food", "medical"]


async def test_get_returns_saved_preferences(client, make_user, login):
    donor = await make_user("donor")
    async with SessionFactory() as session:
        await factories.create_donor_preference(
            session,
            donor=donor,
            causes=["education"],
            budget=500.0,
            location="Nairobi",
        )
        await session.commit()

    response = client.get(f"{API}/donors/preferences/", headers=login(donor))
    assert response.status_code == 200, response.text
    assert response.json()["causes"] == ["education"]


async def test_unknown_cause_is_rejected(client, make_user, login):
    donor = await make_user("donor")
    response = client.put(
        f"{API}/donors/preferences/",
        headers=login(donor),
        json={"causes": ["unicorns"]},
    )
    assert response.status_code == 422


async def test_preferences_are_scoped_to_the_donor(client, make_user, login):
    donor_a = await make_user("donor", email="pref-a@example.org")
    donor_b = await make_user("donor", email="pref-b@example.org")
    async with SessionFactory() as session:
        await factories.create_donor_preference(
            session, donor=donor_a, causes=["housing"], budget=1000.0
        )
        await session.commit()

    response = client.get(f"{API}/donors/preferences/", headers=login(donor_b))
    assert response.status_code == 200, response.text
    assert response.json() is None, "donor B must never see donor A's row"


async def test_non_donor_is_denied(client, make_user, login):
    member = await make_user("community_member")
    response = client.get(f"{API}/donors/preferences/", headers=login(member))
    assert response.status_code == 403