"""Urgency calibration: dataset integrity, model behaviour, and the gate.

Three failure modes are guarded here:

1. the labeled urgency dataset drifting, losing balance, or disagreeing with
   its generator (same discipline as the category set),
2. a calibrator whose priority output is out of the declared contract, and
3. an urgency gate that passes everything (mirror of the classifier gate
   tests: `gate_check` is pinned with deliberately bad input).
"""

import sys
from pathlib import Path

import pytest

AI_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = AI_DIR / "eval"
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(AI_DIR))

from build_urgency_dataset import (  # noqa: E402
    BAND_ORDER,
    URGENCY_SOURCE,
    build_rows,
)
from evaluate_urgency import (  # noqa: E402
    evaluate_calibrator,
    gate_check,
    load_rows,
)

from faithbridge_ai.calibration import (  # noqa: E402
    BAND_CENTRES,
    FALLBACK_ENGINE,
    URGENCY_ENGINE,
    UrgencyCalibrator,
    priority_of,
)

ROWS_PER_BAND = 20
EXPECTED_ROWS = len(BAND_ORDER) * ROWS_PER_BAND

MIN_ACCURACY = 0.70
MIN_BAND = 0.50


@pytest.fixture(scope="module")
def rows():
    return load_rows()


@pytest.fixture(scope="module")
def result():
    return evaluate_calibrator()


# --- dataset integrity --------------------------------------------------------


def test_row_count(rows):
    assert len(rows) == EXPECTED_ROWS


def test_every_band_is_present_and_balanced(rows):
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["band"]] = counts.get(row["band"], 0) + 1
    assert set(counts) == set(BAND_ORDER)
    assert set(counts.values()) == {ROWS_PER_BAND}


def test_score_colours_stay_inside_their_band(rows):
    for row in rows:
        score = row["urgency_score"]
        if row["band"] == "low":
            assert 0 <= score < 40, row
        elif row["band"] == "medium":
            assert 40 <= score < 60, row
        elif row["band"] == "high":
            assert 60 <= score < 80, row
        else:
            assert score >= 80, row


def test_no_duplicate_texts(rows):
    texts = [row["text"] for row in rows]
    duplicates = {t for t in texts if texts.count(t) > 1}
    assert not duplicates, f"duplicate statements: {duplicates}"


def test_generator_matches_committed_dataset(rows):
    assert build_rows() == [
        (r["text"], r["urgency_score"], r["band"], r["source"]) for r in rows
    ]


def test_generator_is_deterministic():
    assert build_rows() == build_rows()


def test_every_row_declares_synthetic_provenance(rows):
    assert {row["source"] for row in rows} == {URGENCY_SOURCE}


# --- model contract -----------------------------------------------------------


def test_priority_of_follows_the_band_boundaries():
    assert priority_of(0) == "low"
    assert priority_of(39) == "low"
    assert priority_of(40) == "medium"
    assert priority_of(59) == "medium"
    assert priority_of(60) == "high"
    assert priority_of(79) == "high"
    assert priority_of(80) == "critical"
    assert priority_of(100) == "critical"


def test_band_centres_are_valid_and_exhaustive():
    assert set(BAND_CENTRES) == set(BAND_ORDER)
    for band in BAND_ORDER:
        assert 0 <= BAND_CENTRES[band] <= 100
        assert isinstance(BAND_CENTRES[band], int)


def test_predict_returns_the_contract_dict():
    calibrator = UrgencyCalibrator()
    assert not calibrator.is_fitted
    calibrator.fit(
        ["help us this week", "we need food", "could use guidance soon"],
        ["medium", "high", "low"],
    )
    assert calibrator.is_fitted

    prediction = calibrator.predict("random text")
    assert prediction["priority"] in BAND_ORDER
    assert isinstance(prediction["urgency_score"], int)
    assert 0 <= prediction["urgency_score"] <= 100
    assert prediction["urgency_score"] == BAND_CENTRES[prediction["priority"]]


def test_unfitted_calibrator_raises():
    with pytest.raises(RuntimeError):
        UrgencyCalibrator().predict("anything")


def test_calibrated_urgency_is_additive_to_classify_contract():
    """baseline.classify must still satisfy the AI service contract keys."""
    from faithbridge_ai import baseline

    result = baseline.classify("We are being evicted tomorrow and need help tonight")
    assert set(result) >= {"category", "urgency_score", "priority"}
    assert result["urgency_engine"] in {URGENCY_ENGINE, FALLBACK_ENGINE}


# --- the gate ----------------------------------------------------------------


def test_overall_band_accuracy_meets_gate(result):
    assert result["accuracy"] >= MIN_ACCURACY, (
        f"band accuracy {result['accuracy']:.3f} below {MIN_ACCURACY}"
    )


def test_every_band_reports_precision_and_recall(result):
    for band in BAND_ORDER:
        assert band in result["band_report"]
        stats = result["band_report"][band]
        assert stats["precision"] >= MIN_BAND, f"{band} precision {stats['precision']}"
        assert stats["recall"] >= MIN_BAND, f"{band} recall {stats['recall']}"


def test_gate_reports_all_four_bands():
    result = evaluate_calibrator()
    assert set(result["band_report"]) == set(BAND_ORDER)


def test_gate_fails_on_a_weak_band():
    weak = {
        "accuracy": 0.80,
        "band_report": {
            band: {"precision": 0.9, "recall": 0.9}
            for band in BAND_ORDER
            if band != "critical"
        }
        | {"critical": {"precision": 0.4, "recall": 0.9}},
    }
    failures = gate_check(weak, band_floor=MIN_BAND)
    assert any("critical precision" in failure for failure in failures)


def test_gate_fails_on_low_overall_accuracy():
    weak = {
        "accuracy": 0.20,
        "band_report": {
            band: {"precision": 0.9, "recall": 0.9} for band in BAND_ORDER
        },
    }
    failures = gate_check(weak, band_floor=MIN_BAND, min_accuracy=MIN_ACCURACY)
    assert failures


def test_gate_passes_a_genuinely_good_result():
    good = {
        "accuracy": 0.90,
        "band_report": {
            band: {"precision": 0.88, "recall": 0.86} for band in BAND_ORDER
        },
    }
    assert gate_check(good, band_floor=MIN_BAND, min_accuracy=MIN_ACCURACY) == []