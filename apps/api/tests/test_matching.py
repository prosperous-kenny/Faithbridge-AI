"""Phase 3 donor matching: ranked programs plus consent-clean case counts.

The exit gate for matching is exercised here against the real schema: saved
preferences and inline overrides feed the AI ranker, results are validated
fail-closed, and open-case counts never leak a beneficiary identity (PRD §22)
— a linked, non-consenting person must not surface even as a number.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"


def _stub_ai(monkeypatch, *, available: bool = True, build=None) -> dict:
    """Stub the AI boundary with a deterministic ranker and a spy on the
    payload the API sent, so tests can assert what the API actually asked for.
    """
    spy: dict = {}

    async def _available() -> bool:
        return available

    async def _match(payload: dict) -> dict:
        spy["payload"] = payload
        if build is not None:
            matches = build(payload)
        else:
            matches = [
                {
                    "program_id": program["program_id"],
                    "match_score": round(max(0.0, 1.0 - index * 0.1), 3),
                    "matches_causes": True,
                    "matches_budget": True,
                    "matches_location": True,
                    "reason": "ranked by the test ranker",
                }
                for index, program in enumerate(payload["programs"])
            ]
        return {"engine": "tfidf-sparse-embedding", "matches": matches}

    monkeypatch.setattr("app.api.routes.ai.ai_service_available", _available)
    monkeypatch.setattr("app.api.routes.ai.call_ai_match_donors", _match)
    return spy


async def _seed_program_with_open_cases(*, consented_case: bool = True) -> int:
    """A program whose org carries one pending case in its category."""
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        program = await factories.create_program(
            session,
            organization=org,
            name="Food Pantry Central",
            category="food",
        )
        await factories.create_assistance_request(
            session,
            consented=consented_case,
            linked_user=True,
            category="food",
            organization=org,
        )
        await session.commit()
        return program.id


async def _seed_active_program() -> int:
    """Any active program, so the AI call actually happens (empty pools short
    circuit before the spy is fed)."""
    async with SessionFactory() as session:
        program = await factories.create_program(
            session, name="Generic Program", category="housing"
        )
        await session.commit()
        return program.id


async def test_donor_match_returns_ranked_programs_with_open_cases(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    program_id = await _seed_program_with_open_cases(consented_case=True)
    donor = await make_user("donor")
    async with SessionFactory() as session:
        await factories.create_donor_preference(
            session, donor=donor, causes=["food"], budget=1000.0, location="Lagos"
        )
        await session.commit()

    response = client.post(
        f"{API}/ai/match-donors",
        headers=login(donor),
        json={},  # fall back to saved preferences
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine"] == "tfidf-sparse-embedding"
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["program_id"] == program_id
    assert match["match_score"] == 1.0
    assert match["open_cases"] == 1
    assert match["reason"]


async def test_match_response_never_leaks_beneficiary_identity(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    program_id = await _seed_program_with_open_cases(consented_case=True)
    donor = await make_user("donor")

    response = client.post(
        f"{API}/ai/match-donors",
        headers=login(donor),
        json={"causes": ["food"]},
    )
    assert response.status_code == 200, response.text

    async with SessionFactory() as session:
        beneficiary_email = (
            await session.execute(
                select(factories.User.email)
                .join(factories.Beneficiary, factories.Beneficiary.user_id == factories.User.id)
                .where(factories.Beneficiary.organization_id.isnot(None))
                .limit(1)
            )
        ).scalars().first()

    text = response.text
    assert beneficiary_email not in text
    for forbidden in ("beneficiary", "household_size", "consented", "@example.org"):
        assert forbidden not in text.lower()
    assert str(program_id) in text


async def test_matching_uses_saved_preferences_when_body_is_empty(
    client, make_user, login, monkeypatch
):
    spy = _stub_ai(monkeypatch)
    await _seed_active_program()
    donor = await make_user("donor")
    async with SessionFactory() as session:
        await factories.create_donor_preference(
            session, donor=donor, causes=["housing"], budget=5000.0, location="Lagos"
        )
        await session.commit()

    response = client.post(
        f"{API}/ai/match-donors", headers=login(donor), json={}
    )
    assert response.status_code == 200, response.text

    sent = spy["payload"]
    assert sent["causes"] == ["housing"]
    assert sent["budget"] == 5000.0
    assert sent["location"] == "Lagos"


async def test_inline_overrides_beat_saved_preferences(
    client, make_user, login, monkeypatch
):
    spy = _stub_ai(monkeypatch)
    await _seed_active_program()
    donor = await make_user("donor")
    async with SessionFactory() as session:
        await factories.create_donor_preference(
            session, donor=donor, causes=["housing"]
        )
        await session.commit()

    response = client.post(
        f"{API}/ai/match-donors",
        headers=login(donor),
        json={"causes": ["education"], "budget": 3000, "location": "Kampala"},
    )
    assert response.status_code == 200, response.text

    sent = spy["payload"]
    assert sent["causes"] == ["education"]
    assert sent["budget"] == 3000.0
    assert sent["location"] == "Kampala"


async def test_donor_without_preferences_and_without_overrides_gets_400(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    donor = await make_user("donor")
    response = client.post(f"{API}/ai/match-donors", headers=login(donor), json={})
    assert response.status_code == 400
    assert "preferences" in response.json()["detail"]


async def test_unavailable_ai_service_is_503(client, make_user, login, monkeypatch):
    _stub_ai(monkeypatch, available=False)
    donor = await make_user("donor")
    response = client.post(
        f"{API}/ai/match-donors",
        headers=login(donor),
        json={"causes": ["food"]},
    )
    assert response.status_code == 503


async def test_matches_from_programs_outside_the_pool_fail_closed(
    client, make_user, login, monkeypatch
):
    _stub_ai(
        monkeypatch,
        build=lambda payload: [
            {
                "program_id": 999999,
                "match_score": 1.0,
                "matches_causes": True,
                "matches_budget": True,
                "matches_location": True,
                "reason": "hallucinated program",
            }
        ],
    )
    await _seed_program_with_open_cases()
    donor = await make_user("donor")
    response = client.post(
        f"{API}/ai/match-donors",
        headers=login(donor),
        json={"causes": ["food"]},
    )
    assert response.status_code == 503


async def test_out_of_range_or_missing_score_fails_closed(
    client, make_user, login, monkeypatch
):
    program_id = await _seed_program_with_open_cases()
    for bad_score in (1.5, -0.2, "high"):
        _stub_ai(
            monkeypatch,
            build=lambda payload, score=bad_score: [
                {
                    "program_id": payload["programs"][0]["program_id"],
                    "match_score": score,
                    "matches_causes": True,
                    "matches_budget": True,
                    "matches_location": True,
                    "reason": "noisy score",
                }
            ],
        )
        donor = await make_user("donor")
        response = client.post(
            f"{API}/ai/match-donors",
            headers=login(donor),
            json={"causes": ["food"]},
        )
        assert response.status_code == 503, f"score {bad_score!r} must fail closed"
    assert program_id is not None


async def test_unknown_engine_fails_closed(client, make_user, login, monkeypatch):
    _stub_ai(monkeypatch)
    await _seed_active_program()

    async def _match(payload: dict) -> dict:
        return {"engine": "torch-sbert-2027", "matches": []}

    monkeypatch.setattr("app.api.routes.ai.call_ai_match_donors", _match)
    donor = await make_user("donor")
    response = client.post(
        f"{API}/ai/match-donors",
        headers=login(donor),
        json={"causes": ["food"]},
    )
    assert response.status_code == 503


async def test_open_cases_exclude_non_consenting_linked_beneficiaries(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        program = await factories.create_program(
            session, organization=org, name="Case Load Program", category="education"
        )
        # consenting linked person: counts
        await factories.create_assistance_request(
            session, consented=True, linked_user=True, category="education", organization=org
        )
        # linked but NOT consented: must not count (PRD §22)
        await factories.create_assistance_request(
            session, consented=False, linked_user=True, category="education", organization=org
        )
        # anonymous consenting beneficiary (no linked account): counts
        await factories.create_assistance_request(
            session, consented=True, linked_user=False, category="education", organization=org
        )
        # terminal status: no longer "open"
        done_request, _, _ = await factories.create_assistance_request(
            session, consented=True, linked_user=True, category="education", organization=org
        )
        done_request.status = "fulfilled"
        # a different category in the same org: not this program's load
        await factories.create_assistance_request(
            session, consented=True, linked_user=True, category="food", organization=org
        )
        await session.commit()
        program_id = program.id

    donor = await make_user("donor")
    response = client.post(
        f"{API}/ai/match-donors",
        headers=login(donor),
        json={"causes": ["education"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["matches"][0]["program_id"] == program_id
    assert response.json()["matches"][0]["open_cases"] == 2


async def test_non_donor_is_denied_matching(client, make_user, login, monkeypatch):
    _stub_ai(monkeypatch)
    member = await make_user("community_member")
    response = client.post(
        f"{API}/ai/match-donors",
        headers=login(member),
        json={"causes": ["food"]},
    )
    assert response.status_code == 403