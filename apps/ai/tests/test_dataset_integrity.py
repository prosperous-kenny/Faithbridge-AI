"""Dataset integrity and gate-effectiveness tests for task 5.

Two things are easy to get wrong and expensive to miss:

1. A dataset that silently loses rows, gains duplicates, or drifts out of
   balance would quietly change what the accuracy number means.
2. `gate_check` returning an empty list on everything would make the whole
   accuracy gate vacuous while every other test still passed. These tests pin
   the gate down with deliberately bad input.
"""

import sys
from pathlib import Path

import pytest

AI_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = AI_DIR / "eval"
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(AI_DIR))

from build_dataset import CATEGORIES, TEMPLATE_SOURCE, build_rows  # noqa: E402
from evaluate import gate_check, load_rows, provenance, render_provenance  # noqa: E402

EXPECTED_ROWS = 204
ROWS_PER_CATEGORY = 34


@pytest.fixture(scope="module")
def rows():
    return load_rows()


def test_row_count(rows):
    assert len(rows) == EXPECTED_ROWS


def test_every_category_is_balanced(rows):
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    assert set(counts) == set(CATEGORIES)
    assert set(counts.values()) == {ROWS_PER_CATEGORY}


def test_no_duplicate_texts(rows):
    texts = [row["text"] for row in rows]
    duplicates = {t for t in texts if texts.count(t) > 1}
    assert not duplicates, f"duplicate statements in the dataset: {duplicates}"


def test_no_blank_fields(rows):
    for row in rows:
        assert row["text"].strip(), "blank text"
        assert row["category"].strip(), "blank category"
        assert row["source"].strip(), "unlabeled provenance"


def test_every_row_declares_its_source(rows):
    assert {row["source"] for row in rows} == {TEMPLATE_SOURCE}


def test_generator_matches_committed_dataset(rows):
    """The committed CSV must be exactly what the generator produces."""
    assert build_rows() == [(r["text"], r["category"], r["source"]) for r in rows]


def test_generator_is_deterministic():
    assert build_rows() == build_rows()


def test_provenance_is_reported_and_flagged_as_synthetic(rows):
    counts = provenance(rows)
    assert counts == {TEMPLATE_SOURCE: EXPECTED_ROWS}
    rendered = "\n".join(render_provenance(rows))
    assert TEMPLATE_SOURCE in rendered
    assert "WARNING" in rendered
    assert "not field accuracy" in rendered


def test_provenance_warning_disappears_once_real_data_is_present(rows):
    """When real submissions land, the warning must not keep firing."""
    mixed = rows + [
        {"text": "a real submission", "category": "food", "source": "submission"}
    ]
    assert "WARNING" not in "\n".join(render_provenance(mixed))


def test_gate_fails_on_low_overall_accuracy():
    """Guards against a gate that passes everything."""
    bad = {
        "name": "broken",
        "accuracy": 0.42,
        "report": {
            category: {"precision": 1.0, "recall": 1.0} for category in CATEGORIES
        },
    }
    failures = gate_check(bad, threshold=0.85, floor=0.70)
    assert failures
    assert any("0.420" in failure for failure in failures)


def test_gate_fails_on_a_weak_category():
    bad = {
        "name": "mostly good",
        "accuracy": 0.93,
        "report": {
            category: {"precision": 1.0, "recall": 1.0}
            for category in CATEGORIES
            if category != "education"
        }
        | {"education": {"precision": 1.0, "recall": 0.41}},
    }
    failures = gate_check(bad, threshold=0.85, floor=0.70)
    assert any("education recall" in failure for failure in failures)


def test_gate_fails_on_weak_precision_not_just_recall():
    bad = {
        "name": "over-predicting",
        "accuracy": 0.93,
        "report": {
            category: {"precision": 1.0, "recall": 1.0}
            for category in CATEGORIES
            if category != "housing"
        }
        | {"housing": {"precision": 0.52, "recall": 0.95}},
    }
    failures = gate_check(bad, threshold=0.85, floor=0.70)
    assert any("housing precision" in failure for failure in failures)


def test_gate_passes_a_genuinely_good_result():
    good = {
        "name": "good",
        "accuracy": 0.91,
        "report": {
            category: {"precision": 0.9, "recall": 0.88} for category in CATEGORIES
        },
    }
    assert gate_check(good, threshold=0.85, floor=0.70) == []
