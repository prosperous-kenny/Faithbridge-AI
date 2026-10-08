"""Donor-matching gate: dataset integrity, the top-3 precision gate, and
negative checks that the gate cannot pass on weak input.

Mirrors the discipline of the classifier and urgency gate tests: the labelled
dataset must stay in lock-step with its generator, every label must be a
reachable program from the pool it claims to rank, and `gate_check` must fail
when fed deliberately bad results.
"""

import sys
from pathlib import Path

import pytest

AI_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = AI_DIR / "eval"
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(AI_DIR))


from build_matching_dataset import (  # noqa: E402
    MATCHING_SOURCE,
    POOL,
    PROFILES,
    PROGRAM_IDS,
    build_rows,
)
from evaluate_matching import (  # noqa: E402
    evaluate_matching,
    gate_check,
    load_rows,
)

MIN_TOP3 = 0.70
EXPECTED_ROWS = 15
EXPECTED_PER_DONOR = 3

CATEGORY_OF_PROGRAM = {program[0]: program[2] for program in POOL}


@pytest.fixture(scope="module")
def rows():
    return load_rows()


@pytest.fixture(scope="module")
def result():
    return evaluate_matching()


# --- labelled data integrity -------------------------------------------------


def test_row_count(rows):
    assert len(rows) == EXPECTED_ROWS


def test_donor_ids_are_the_unique_sequence(rows):
    assert {row["donor_id"] for row in rows} == set(range(1, EXPECTED_ROWS + 1))


def test_every_label_is_three_reachable_programs(rows):
    for row in rows:
        assert len(row["expected"]) == EXPECTED_PER_DONOR, row
        for program_id in row["expected"]:
            assert program_id in PROGRAM_IDS, (program_id, row)


def test_labels_respect_the_cause_constraint(rows):
    for row in rows:
        if not row["causes"]:
            continue
        for program_id in row["expected"]:
            assert CATEGORY_OF_PROGRAM[program_id] in row["causes"], (program_id, row)


def test_generator_matches_committed_dataset(rows):
    generated = build_rows()
    assert len(generated) == len(rows)
    for donor_id, causes, budget, location, expected, source in generated:
        row = next(r for r in rows if r["donor_id"] == donor_id)
        assert row["causes"] == [c for c in causes.split(",") if c]
        assert row["budget"] == float(budget)
        assert row["location"] == (location or None)
        assert row["expected"] == [int(p) for p in expected.split(",") if p]
        assert row["source"] == source


def test_generator_is_deterministic():
    assert build_rows() == build_rows()


def test_every_profile_declares_synthetic_provenance(rows):
    assert {row["source"] for row in rows} == {MATCHING_SOURCE}


def test_profiles_and_pool_have_the_declared_shape():
    assert len(POOL) == 18
    assert len(PROFILES) == EXPECTED_ROWS
    assert sorted({program[2] for program in POOL}) == [
        "education",
        "emergency",
        "employment",
        "food",
        "housing",
        "medical",
    ]


# --- the gate ----------------------------------------------------------------


def test_top3_precision_meets_the_gate(result):
    mean = sum(r["precision"] for r in result["per_donor"]) / result["rows"]
    assert mean >= MIN_TOP3, f"top-3 precision {mean:.3f} below {MIN_TOP3}"


def test_no_donor_is_shut_out_of_the_top_three(result):
    for donor in result["per_donor"]:
        assert 0 <= donor["precision"] <= 1
        assert donor["precision"] > 0, (
            f"donor #{donor['donor_id']} found none of its expected programs "
            f"in the top three"
        )


def test_gate_passes_the_real_result(result):
    assert gate_check(result, min_top3=MIN_TOP3) == []


def test_gate_fails_on_low_overall_precision():
    weak = {
        "rows": 15,
        "per_donor": [
            {"donor_id": i, "precision": 0.1, "expected": [i]}
            for i in range(15)
        ],
    }
    failures = gate_check(weak, min_top3=MIN_TOP3)
    assert any("top-3 precision" in failure for failure in failures)


def test_gate_fails_when_a_donor_finds_nothing():
    result = evaluate_matching()
    result["per_donor"][0]["precision"] = 0.0
    failures = gate_check(result, min_top3=MIN_TOP3)
    assert any("donor #1" in failure for failure in failures)