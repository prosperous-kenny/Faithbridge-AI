"""Guard the Phase 0 accuracy gate so a regression fails CI.

Thresholds mirror the Phase 0 exit gate in docs/IMPLEMENTATION_PLAN.md:
overall accuracy >= 85%, and no category below 70% on precision or recall.
The dataset is template-generated (see eval/report.md), so this test protects
against regression, not field accuracy.
"""

import sys
from pathlib import Path

import pytest

AI_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = AI_DIR / "eval"
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(AI_DIR))

from evaluate import evaluate_model, gate_check  # noqa: E402

MIN_ACCURACY = 0.85
MIN_CATEGORY = 0.70


@pytest.fixture(scope="module")
def result():
    return evaluate_model("TF-IDF + LinearSVC", "tfidf")


def test_overall_accuracy_meets_gate(result):
    assert result["accuracy"] >= MIN_ACCURACY, (
        f"overall accuracy {result['accuracy']:.3f} below {MIN_ACCURACY}"
    )


def test_no_category_below_floor(result):
    failures = gate_check(result, threshold=MIN_ACCURACY, floor=MIN_CATEGORY)
    assert not failures, "gate failures: " + "; ".join(failures)


def test_education_is_weakest_but_above_floor(result):
    """Education is the known weak category; guard it explicitly."""
    education = result["report"]["education"]
    assert education["recall"] >= MIN_CATEGORY
    assert education["precision"] >= MIN_CATEGORY


def test_beats_rule_based_baseline(result):
    """The new model must beat what it replaces, or the swap is unjustified."""
    rules = evaluate_model("rule-based", "rules")
    assert result["accuracy"] > rules["accuracy"], (
        f"TF-IDF {result['accuracy']:.3f} does not beat rule-based "
        f"{rules['accuracy']:.3f}"
    )
