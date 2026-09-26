import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Organization, User
from app.db.session import Base, SessionFactory, engine


@pytest.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
async def test_round_trip_insert_and_select():
    async with SessionFactory() as session:
        session.add(Organization(name="Grace Community Church", org_type="church"))
        session.add(
            User(
                email="leader@grace.example",
                full_name="Test Leader",
                role="faith_leader",
            )
        )
        await session.commit()

    async with SessionFactory() as session:
        orgs = (await session.execute(select(Organization))).scalars().all()
        users = (await session.execute(select(User))).scalars().all()

    assert len(orgs) == 1
    assert orgs[0].name == "Grace Community Church"
    assert orgs[0].created_at is not None
    assert len(users) == 1
    assert users[0].role == "faith_leader"


@pytest.mark.asyncio
async def test_unique_email_constraint():
    async with SessionFactory() as session:
        session.add(User(email="dupe@example.org", full_name="A", role="donor"))
        await session.commit()

    async with SessionFactory() as session:
        session.add(User(email="dupe@example.org", full_name="B", role="donor"))
        with pytest.raises(IntegrityError):
            await session.commit()
