"""Phase 2 assistance lifecycle: submission -> triage -> approve/decline.

Covers the Phase 2 exit gate's "full flow application" against the real schema
and a live Postgres test database (the conftest client rebuilds it via Alembic
every session): persistence of a classified submission, the lifecycle state
machine, org scoping, the tamper-evident audit chain, and the fail-closed
behaviour of the AI boundary.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import AssistanceRequest, AuditLog, Beneficiary, Organization
from app.db.session import SessionFactory
from app.repositories.audit import verify_chain
from app.services.assistance import (
    LIFE_CYCLE,
    VALID_STATUSES,
    LifecycleError,
    assert_transition,
)
from tests import factories

API = "/api/v1"


def _dled(text: str) -> dict:
    """Deterministic classification the tests can assert against."""
    return {"category": "housing", "urgency_score": 72, "priority": "high"}


def _stub_ai(monkeypatch) -> None:
    async def _available() -> bool:
        return True

    async def _classify(text: str) -> dict:
        return _dled(text)

    monkeypatch.setattr("app.api.routes.assistance.ai_service_available", _available)
    monkeypatch.setattr("app.api.routes.assistance.classify_need", _classify)


def _stub_background(monkeypatch, calls: list[str]) -> None:
    """Replace both background tasks with spies that record ``kind:id``."""

    async def _notify(*args):
        calls.append(f"notify:{args[0]}")

    async def _rescore(*args):
        calls.append(f"rescore:{args[0]}")

    monkeypatch.setattr(
        "app.api.routes.assistance.notify_new_critical_request", _notify
    )
    monkeypatch.setattr("app.api.routes.assistance.rescore_request", _rescore)


async def _new_org() -> int:
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        return org.id


async def _seed_request(priority: str = "high", status: str = "submitted") -> int:
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        request, _, _ = await factories.create_assistance_request(
            session, priority=priority, organization=org
        )
        request.status = status
        await session.commit()
        return request.id


# --- the state machine itself ------------------------------------------------


def test_lifecycle_matrix_is_exactly_the_prd_flow():
    assert VALID_STATUSES == {
        "submitted",
        "triaged",
        "approved",
        "fulfilled",
        "declined",
    }
    assert LIFE_CYCLE["submitted"] == {"triaged", "declined"}
    assert LIFE_CYCLE["triaged"] == {"approved", "declined"}
    assert LIFE_CYCLE["approved"] == {"fulfilled", "declined"}
    # Terminal states: nothing leaves them.
    assert LIFE_CYCLE["fulfilled"] == set()
    assert LIFE_CYCLE["declined"] == set()


def test_good_path_transitions_are_allowed():
    assert_transition("submitted", "triaged")
    assert_transition("triaged", "approved")
    assert_transition("approved", "fulfilled")
    assert_transition("submitted", "declined")
    assert_transition("triaged", "declined")
    assert_transition("approved", "declined")


def test_illegal_and_terminal_transitions_raise():
    for current, target in [
        ("submitted", "approved"),
        ("submitted", "fulfilled"),
        ("triaged", "fulfilled"),
        ("approved", "triaged"),
        ("fulfilled", "approved"),
        ("declined", "submitted"),
        ("declined", "approved"),
        ("nonsense", "triaged"),
        ("submitted", "nonsense"),
    ]:
        try:
            assert_transition(current, target)
        except LifecycleError:
            continue
        raise AssertionError(f"{current!r} -> {target!r} should be illegal")


def test_repeat_transitions_into_same_terminal_state_are_illegal():
    # Once declined, a second decline from anywhere is also rejected because
    # the first decline already left the org chart of valid successors.
    try:
        assert_transition("declined", "declined")
    except LifecycleError:
        return
    raise AssertionError("declined -> declined should be illegal")


# --- submission persists a classified request --------------------------------


async def test_submission_persists_and_binds_beneficiary(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    background_calls: list[str] = []
    _stub_background(monkeypatch, background_calls)

    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)

    response = client.post(
        f"{API}/assistance/requests",
        headers=login(member),
        json={
            "organization_id": org_id,
            "description": "Rent is overdue and we need help before the end of the month",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["status"] == "submitted"
    assert body["category"] == "housing"
    assert body["priority"] == "high"
    assert body["urgency_score"] == 72
    assert body["organization_id"] == org_id

    async with SessionFactory() as session:
        from sqlalchemy.orm import selectinload

        request = (
            await session.execute(
                select(AssistanceRequest)
                .where(AssistanceRequest.id == body["id"])
                .options(selectinload(AssistanceRequest.beneficiary))
            )
        ).scalar_one()
        assert request is not None
        assert request.status == "submitted"
        assert request.category == "housing"
        assert request.beneficiary.user_id == member.id
        assert request.beneficiary.consented_at is not None

    assert background_calls == [f"notify:{body['id']}"]


async def test_submission_reuses_the_submitters_beneficiary(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)
    headers = login(member)
    payload = {
        "organization_id": org_id,
        "description": "We need help buying food for the week",
    }

    first = client.post(f"{API}/assistance/requests", headers=headers, json=payload)
    second = client.post(f"{API}/assistance/requests", headers=headers, json=payload)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"], "each submission is a request"

    async with SessionFactory() as session:
        beneficiary_ids = (
            await session.execute(
                select(Beneficiary.id).where(Beneficiary.user_id == member.id)
            )
        ).scalars().all()
        assert len(beneficiary_ids) == 1, "one member maps to one beneficiary"


# --- org scoping -------------------------------------------------------------


async def test_member_cannot_submit_to_another_org(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    org_a = await _new_org()
    org_b = await _new_org()
    member = await make_user("community_member", organization_id=org_a)

    response = client.post(
        f"{API}/assistance/requests",
        headers=login(member),
        json={
            "organization_id": org_b,
            "description": "Please help us with groceries this month",
        },
    )
    assert response.status_code == 403


async def test_leader_sees_only_their_orgs_queue(client, make_user, login):
    org_a_id = await _new_org()
    org_b_id = await _new_org()
    async with SessionFactory() as session:
        org_a = await session.get(Organization, org_a_id)
        org_b = await session.get(Organization, org_b_id)
        await factories.create_assistance_request(session, organization=org_a)
        await factories.create_assistance_request(session, organization=org_b)
        await session.commit()

    leader = await make_user("faith_leader", organization_id=org_a_id)
    response = client.get(f"{API}/assistance/requests", headers=login(leader))
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]["beneficiary"]["organization_id"] == org_a_id


async def test_leader_cannot_patch_another_orgs_case(client, make_user, login):
    org_a_id = await _new_org()
    org_b_id = await _new_org()
    async with SessionFactory() as session:
        org_b = await session.get(Organization, org_b_id)
        request, _, _ = await factories.create_assistance_request(
            session, organization=org_b
        )
        await session.commit()
        request_id = request.id

    leader = await make_user("faith_leader", organization_id=org_a_id)
    response = client.patch(
        f"{API}/assistance/requests/{request_id}/status",
        headers=login(leader),
        json={"status": "triaged"},
    )
    assert response.status_code == 403


# --- lifecycle over the API, with an intact audit chain ----------------------


async def test_full_lifecycle_with_audit_chain(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    background_calls: list[str] = []
    _stub_background(monkeypatch, background_calls)

    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)
    leader = await make_user("faith_leader", organization_id=org_id)

    created = client.post(
        f"{API}/assistance/requests",
        headers=login(member),
        json={
            "organization_id": org_id,
            "description": "Our family is being evicted and needs help urgently",
        },
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    triaged = client.patch(
        f"{API}/assistance/requests/{request_id}/status",
        headers=login(leader),
        json={"status": "triaged", "note": "contacted family; credible"},
    )
    assert triaged.status_code == 200, triaged.text
    assert triaged.json()["status"] == "triaged"

    approved = client.patch(
        f"{API}/assistance/requests/{request_id}/status",
        headers=login(leader),
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    fulfilled = client.patch(
        f"{API}/assistance/requests/{request_id}/status",
        headers=login(leader),
        json={"status": "fulfilled"},
    )
    assert fulfilled.status_code == 200
    assert fulfilled.json()["status"] == "fulfilled"

    # A notification runs on submission; a rescore is scheduled exactly once,
    # on the triage step.
    assert background_calls == [
        f"notify:{request_id}",
        f"rescore:{request_id}",
    ]

    async with SessionFactory() as session:
        assert await verify_chain(session) == []
        actions = (
            await session.execute(
                select(AuditLog.action).where(AuditLog.entity_id == str(request_id))
            )
        ).scalars().all()
        assert list(actions) == [
            "assistance.request.submitted",
            "assistance.request.status.triaged",
            "assistance.request.status.approved",
            "assistance.request.status.fulfilled",
        ]


async def test_tampered_audit_row_is_detected(client, make_user, login, monkeypatch):
    """The hash chain must notice a rewritten note."""
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)
    leader = await make_user("faith_leader", organization_id=org_id)

    created = client.post(
        f"{API}/assistance/requests",
        headers=login(member),
        json={
            "organization_id": org_id,
            "description": "A family in our building needs shelter after the fire",
        },
    )
    request_id = created.json()["id"]
    client.patch(
        f"{API}/assistance/requests/{request_id}/status",
        headers=login(leader),
        json={"status": "triaged", "note": "original note"},
    )

    async with SessionFactory() as session:
        entry = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "assistance.request.status.triaged"
                )
            )
        ).scalar_one()
        entry.note = "rewritten by an attacker"
        await session.commit()

        violations = await verify_chain(session)
    assert any("mismatch" in violation for violation in violations)


async def test_illegal_transition_is_rejected_and_not_recorded(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)
    leader = await make_user("faith_leader", organization_id=org_id)

    created = client.post(
        f"{API}/assistance/requests",
        headers=login(member),
        json={
            "organization_id": org_id,
            "description": "I need help paying for school fees this term",
        },
    )
    request_id = created.json()["id"]

    response = client.patch(
        f"{API}/assistance/requests/{request_id}/status",
        headers=login(leader),
        json={"status": "fulfilled"},
    )
    assert response.status_code == 409
    assert "submitted" in response.json()["detail"]

    async with SessionFactory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action.contains("fulfilled"))
            )
        ).scalar_one()
        assert count == 0, "a rejected transition must not reach the audit trail"


# --- the AI boundary ---------------------------------------------------------


async def test_invalid_classification_fails_closed(
    client, make_user, login, monkeypatch
):
    async def _available() -> bool:
        return True

    async def _junk(text: str) -> dict:
        return {"category": "unicorn", "urgency_score": 999, "priority": "galactic"}

    monkeypatch.setattr("app.api.routes.assistance.ai_service_available", _available)
    monkeypatch.setattr("app.api.routes.assistance.classify_need", _junk)

    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)

    response = client.post(
        f"{API}/assistance/requests",
        headers=login(member),
        json={
            "organization_id": org_id,
            "description": "We need help with food and rent this week",
        },
    )
    assert response.status_code == 503
    assert "invalid classification" in response.json()["detail"]

    async with SessionFactory() as session:
        count = (
            await session.execute(select(func.count()).select_from(AssistanceRequest))
        ).scalar_one()
        assert count == 0, "nothing may be persisted from an invalid classification"


# --- queue ordering and filtering --------------------------------------------

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


async def test_priority_sort_puts_critical_first(client, make_user, login):
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        for priority in ["high", "critical", "low", "medium"]:
            await factories.create_assistance_request(
                session, priority=priority, organization=org
            )
        await session.commit()

    leader = await make_user("faith_leader")
    response = client.get(
        f"{API}/assistance/requests?sort=priority", headers=login(leader)
    )
    assert response.status_code == 200, response.text
    got = [item["priority"] for item in response.json()]
    assert got == sorted(got, key=PRIORITY_ORDER.__getitem__)
    assert got[0] == "critical"


async def test_status_filter_limits_the_queue(client, make_user, login):
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        triaged, _, _ = await factories.create_assistance_request(
            session, priority="high", organization=org
        )
        triaged.status = "triaged"
        fulfilled, _, _ = await factories.create_assistance_request(
            session, priority="low", organization=org
        )
        fulfilled.status = "fulfilled"
        await session.commit()

    leader = await make_user("faith_leader")
    response = client.get(
        f"{API}/assistance/requests?status=triaged", headers=login(leader)
    )
    assert response.status_code == 200, response.text
    assert [item["priority"] for item in response.json()] == ["high"]