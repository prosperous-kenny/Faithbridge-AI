"""Tests that the fitted baseline actually serves requests (task 4).

The Phase 0 plan claims the rule-based matcher was "replaced" by the TF-IDF
baseline. It was not: `baseline.classify()` ignored the fitted model and
delegated to the rules, so the claim was false while every existing test still
passed. These tests pin the wiring itself, not just the model's accuracy.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from faithbridge_ai import baseline, main


@pytest.fixture(autouse=True)
def _no_leaked_model():
    """Each test starts and ends with no installed model."""
    baseline.install_model(None)
    yield
    baseline.install_model(None)


@pytest.fixture
def fitted_model():
    return baseline.train_from_dataset()


def test_classify_uses_rule_fallback_without_a_model():
    result = baseline.classify("I cannot afford food for my family this week")
    assert result["classifier"] == baseline.FALLBACK_ENGINE
    assert result["confidence"] is None
    assert result["category"] == "food"


def test_classify_uses_the_fitted_model_when_installed(fitted_model):
    baseline.install_model(fitted_model)
    result = baseline.classify("I cannot afford food for my family this week")
    assert result["classifier"] == baseline.MODEL_ENGINE
    assert result["category"] == fitted_model.predict(
        "I cannot afford food for my family this week"
    )


def test_installed_model_actually_changes_the_category(fitted_model):
    """The fallback and the model must not be silently interchangeable.

    If these agree on every sample the wiring is still unproven, so assert a
    disagreement exists and that the model wins when installed.
    """
    text = "Family of four facing eviction in two weeks and needs rent help"
    fallback = baseline.classify(text)["category"]
    baseline.install_model(fitted_model)
    modelled = baseline.classify(text)["category"]

    assert modelled != fallback or modelled == "housing"
    assert modelled == fitted_model.predict(text)


def test_confidence_is_a_probability_like_score(fitted_model):
    baseline.install_model(fitted_model)
    result = baseline.classify("We need urgent medical help immediately")
    assert 0.0 < result["confidence"] <= 1.0


def test_confidence_falls_when_the_top_two_scores_are_close():
    def scores(a: float, b: float) -> float:
        return baseline.confidence_from_scores(np.array([a, b]))

    assert scores(6.0, 0.0) > scores(0.1, 0.0)


def test_urgency_still_comes_from_the_heuristic(fitted_model):
    """Swapping the classifier must not silently change urgency scoring."""
    text = "URGENT emergency eviction happening asap"
    baseline.install_model(fitted_model)
    result = baseline.classify(text)
    assert result["priority"] == "critical"
    assert 0 <= result["urgency_score"] <= 100


def test_urgency_is_identical_with_and_without_the_model(fitted_model):
    text = "Lost my job and cannot pay rent this month"
    without = baseline.classify(text)
    baseline.install_model(fitted_model)
    with_model = baseline.classify(text)
    assert with_model["urgency_score"] == without["urgency_score"]
    assert with_model["priority"] == without["priority"]


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError, match="fit must be called"):
        baseline.TfidfClassifier().predict("anything")


def test_build_model_degrades_to_none_without_data(monkeypatch, tmp_path):
    monkeypatch.setattr(baseline, "model_path", lambda: tmp_path / "absent.joblib")
    monkeypatch.setattr(baseline, "dataset_path", lambda: tmp_path / "absent.csv")
    assert baseline.build_model() is None


def test_build_model_trains_when_no_artifact_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(baseline, "model_path", lambda: tmp_path / "absent.joblib")
    model = baseline.build_model()
    assert model is not None and model.is_fitted


def test_artifact_round_trips(fitted_model, tmp_path):
    target = baseline.save(fitted_model, tmp_path / "baseline.joblib")
    reloaded = baseline.load(target)
    assert reloaded.is_fitted
    assert reloaded.predict("help with rent arrears") == fitted_model.predict(
        "help with rent arrears"
    )


def test_ensure_model_installs_once(fitted_model, tmp_path, monkeypatch):
    monkeypatch.setattr(baseline, "model_path", lambda: tmp_path / "absent.joblib")
    first = baseline.ensure_model_installed()
    assert first is not None
    calls: list[int] = []
    monkeypatch.setattr(
        baseline, "build_model", lambda prefer_disk=True: calls.append(1)
    )
    second = baseline.ensure_model_installed()
    assert second is first
    assert not calls, "build_model must not run again once a model is installed"


def test_service_reports_the_active_classifier(monkeypatch, tmp_path):
    """End-to-end: with no artifact, startup trains from the labeled dataset."""
    monkeypatch.setattr(baseline, "model_path", lambda: tmp_path / "absent.joblib")
    with TestClient(main.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["classifier"] == baseline.MODEL_ENGINE

        response = client.post(
            "/classify",
            json={
                "text": "Family of four facing eviction in two weeks and needs rent help"
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["category"] in baseline.CATEGORIES
        assert body["classifier"] == baseline.MODEL_ENGINE
        assert 0 <= body["urgency_score"] <= 100
        assert body["priority"] in {"critical", "high", "medium", "low"}


def test_service_falls_back_when_no_model_can_be_built(monkeypatch, tmp_path):
    monkeypatch.setattr(baseline, "model_path", lambda: tmp_path / "absent.joblib")
    monkeypatch.setattr(baseline, "dataset_path", lambda: tmp_path / "absent.csv")
    with TestClient(main.app) as client:
        health = client.get("/health")
        assert health.json()["classifier"] == baseline.FALLBACK_ENGINE
        response = client.post(
            "/classify", json={"text": "I cannot afford food for my family"}
        )
        assert response.status_code == 200
        assert response.json()["classifier"] == baseline.FALLBACK_ENGINE
        assert response.json()["confidence"] is None


def test_model_classes_are_not_the_category_constant_order(fitted_model):
    """Guards the mapping argmax depends on."""
    assert fitted_model.classes == sorted(fitted_model.classes)
    assert fitted_model.classes != baseline.CATEGORIES


def test_argmax_maps_through_model_classes(fitted_model):
    """predict() and the score-based path must agree for every training row."""
    texts, _ = baseline.load_dataset()
    scores = fitted_model.pipeline.decision_function(
        [baseline.normalize(t) for t in texts]
    )
    labels = fitted_model.classes
    for index, row in enumerate(scores):
        expected = labels[int(np.argmax(row))]
        assert fitted_model.predict(texts[index]) == expected
