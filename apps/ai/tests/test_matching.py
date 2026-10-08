"""Donor-program matching: ranker behaviour and the service contract.

The Phase 0 ``/match`` stub is gone; these tests pin the replacement ranker's
behaviour (cause constraint, budget/location soft factors, determinism) and the
service contract (``/match-donors`` response shape, engine reporting, and the
removal of the static pool so no stub path can linger).
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

AI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AI_DIR))

from faithbridge_ai import main  # noqa: E402
from faithbridge_ai.matching import (  # noqa: E402
    ENGINE,
    MatchResult,
    Program,
    rank_matches,
)


def _program(
    program_id: int,
    *,
    name: str = "Food Bank",
    category: str = "food",
    description: str = "Groceries for families",
    location: str | None = "Lagos",
    budget_needed: int | None = 400,
    organization_name: str = "Grace Community Church",
) -> Program:
    return Program(
        program_id=program_id,
        name=name,
        category=category,
        description=description,
        location=location,
        budget_needed=budget_needed,
        organization_name=organization_name,
    )


# --- constraints -------------------------------------------------------------


def test_empty_pool_returns_no_matches():
    assert rank_matches(causes=["food"], budget=500, programs=[]) == []


def test_unknown_causes_are_harmless():
    pool = [_program(1)]
    assert rank_matches(causes=["obscure-cause"], budget=500, programs=pool) == []
    assert rank_matches(causes=[], budget=500, programs=pool) != []


def test_cause_is_a_constraint_not_a_scoring_afterthought():
    pool = [
        _program(1, category="food"),
        _program(2, category="medical", location="Lagos", budget_needed=1),
    ]
    results = rank_matches(causes=["food"], budget=10000, programs=pool)
    assert [r.program_id for r in results] == [1]


def test_no_causes_leaves_the_pool_open():
    pool = [
        _program(1, category="food"),
        _program(2, category="medical", location="Accra"),
    ]
    results = rank_matches(causes=[], budget=10000, programs=pool)
    assert {r.program_id for r in results} == {1, 2}


# --- scoring factors ---------------------------------------------------------


def test_budget_bonus_ranks_a_fit_above_an_over_budget_program():
    pool = [
        _program(1, budget_needed=300),
        _program(2, budget_needed=800),
    ]
    results = rank_matches(causes=["food"], budget=500, location="Lagos", programs=pool)
    assert results[0].program_id == 1
    assert results[0].matches_budget is True
    assert results[1].matches_budget is False


def test_location_bonus_ranks_local_above_distant_identical_program():
    pool = [
        _program(1, location="Lagos"),
        _program(2, location="Accra"),
    ]
    results = rank_matches(causes=["food"], budget=500, location="Lagos", programs=pool)
    assert results[0].program_id == 1
    assert results[1].matches_location is False


def test_unset_budget_or_location_stays_neutral():
    pool = [_program(1)]
    results = rank_matches(causes=["food"], budget=0, location=None, programs=pool)
    assert results[0].matches_budget is True
    assert results[0].matches_location is True


# --- output contract ---------------------------------------------------------


def test_scores_are_bounded_sorted_and_deterministic():
    pool = [
        _program(1),
        _program(2, category="medical", description="Clinic visits for families"),
        _program(3, category="housing", description="Rent arrears clearance"),
    ]
    first = rank_matches(causes=["food"], budget=5000, location="Lagos", programs=pool)
    second = rank_matches(causes=["food"], budget=5000, location="Lagos", programs=pool)
    assert first == second
    for result in first:
        assert 0 <= result.match_score <= 1
    scores = [r.match_score for r in first]
    assert scores == sorted(scores, reverse=True)


def test_top_k_limits_the_result_window():
    results = rank_matches(
        causes=["food"], budget=10000, programs=[_program(i) for i in range(1, 6)], top_k=2
    )
    assert len(results) == 2


def test_reason_reads_like_a_human_explanation():
    result = rank_matches(
        causes=["food"], budget=500, location="Lagos",
        programs=[_program(1, organization_name="Grace Community Church")],
    )[0]
    assert isinstance(result, MatchResult)
    assert "Grace Community Church" in result.reason
    assert "Food Assistance" in result.reason
    assert "$500" in result.reason


def test_over_budget_program_tells_the_truth_in_the_reason():
    result = rank_matches(
        causes=["housing"], budget=200, location="Lagos",
        programs=[_program(1, category="housing", budget_needed=900)],
    )[0]
    assert result.matches_budget is False
    assert "over your $200 budget" in result.reason


def test_reason_flags_outside_geography():
    result = rank_matches(
        causes=["food"], budget=500, location="Lagos",
        programs=[_program(1, location="Accra")],
    )[0]
    assert result.matches_location is False
    assert "outside your area" in result.reason


# --- the service endpoint ----------------------------------------------------


def _request_body() -> dict:
    return {
        "causes": ["food", "medical"],
        "budget": 700,
        "location": "Lagos",
        "programs": [
            {
                "program_id": 1,
                "name": "Food Bank",
                "category": "food",
                "description": "Weekly groceries for families",
                "location": "Lagos",
                "budget_needed": 400,
                "organization_name": "Grace Community Church",
            },
            {
                "program_id": 2,
                "name": "Clinic Subsidy",
                "category": "medical",
                "description": "Clinic visits for uninsured families",
                "location": "Lagos",
                "budget_needed": 500,
                "organization_name": "Grace Community Church",
            },
            {
                "program_id": 3,
                "name": "Scholarship Fund",
                "category": "education",
                "description": "Tuition for secondary students",
                "location": "Accra",
                "budget_needed": 900,
                "organization_name": "Hope Food Bank",
            },
        ],
    }


def test_match_donors_returns_ranked_matches():
    with TestClient(main.app) as client:
        response = client.post("/match-donors", json=_request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == ENGINE
    matches = body["matches"]
    assert matches, "the education program must be filtered out, food+medical remain"
    program_ids = [item["program_id"] for item in matches]
    assert set(program_ids) == {1, 2}  # cause constraint drops program 3
    required = {
        "match_score",
        "matches_causes",
        "matches_budget",
        "matches_location",
        "reason",
    }
    assert all(required <= set(item) for item in matches)


def test_match_donors_with_empty_pool_returns_empty():
    with TestClient(main.app) as client:
        response = client.post(
            "/match-donors",
            json={"causes": ["food"], "budget": 500, "programs": []},
        )
    assert response.status_code == 200
    assert response.json()["matches"] == []


def test_health_reports_the_matching_engine():
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["matching"] == ENGINE


def test_static_match_stub_is_gone():
    """The Phase 0 stub served a hard-coded five-program pool on /match with
    'prog-N' ids. The old path and the static ids must not exist anywhere."""
    with TestClient(main.app) as client:
        response = client.post("/match", json={"causes": ["food"], "budget": 500})
    assert response.status_code == 404
    assert not hasattr(main, "_rank")