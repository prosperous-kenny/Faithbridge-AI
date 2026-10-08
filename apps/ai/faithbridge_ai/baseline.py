"""Phase 0 classifier baseline behind one interface (task 4).

The TF-IDF + linear SVM model is the classifier that serves requests. The
rule-based keyword matcher in classifier.py stays available as an explicit
fallback and as the comparison baseline for the eval harness.

Sentence-transformers is deliberately not wired in: it needs a torch download
at runtime, which is too heavy to make the default path. The comparison and the
revisit trigger are recorded in eval/report.md and
docs/adr/0001-model-selection.md.

Responsibilities are split so the swap is auditable:

- `TfidfClassifier` owns the **category** decision (this is the part the
  evaluation harness measures and gates).
- `score_urgency` from classifier.py owns **urgency and priority**, which stay
  on keyword heuristics until Phase 2 calibrates them against labeled data.
"""

import logging
import os
import re
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from faithbridge_ai import calibration
from faithbridge_ai.classifier import classify as rule_classify
from faithbridge_ai.classifier import score_urgency

logger = logging.getLogger(__name__)

CATEGORIES = ["food", "housing", "medical", "education", "employment", "emergency"]

MODEL_ENGINE = "tfidf-linear-svc"
FALLBACK_ENGINE = "rules-keyword-fallback"

AI_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = AI_DIR / "models" / "baseline.joblib"
DEFAULT_DATASET_PATH = AI_DIR / "eval" / "dataset.csv"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def model_path() -> Path:
    return Path(os.getenv("FAITHBRIDGE_MODEL_PATH", DEFAULT_MODEL_PATH))


def dataset_path() -> Path:
    return Path(os.getenv("FAITHBRIDGE_TRAINING_DATA", DEFAULT_DATASET_PATH))


class TfidfClassifier:
    """TF-IDF (word 1-2 grams + char 3-5 grams) into a linear SVM.

    Char n-grams matter here: submitted needs are often misspelled or
    abbreviated, and word-level features alone miss those variants.
    """

    def __init__(self) -> None:
        self.word_vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
            strip_accents="unicode",
        )
        self.char_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=2,
            sublinear_tf=True,
        )
        self.classifier = LinearSVC(C=1.0, class_weight="balanced")
        self.pipeline: Pipeline | None = None

    @property
    def is_fitted(self) -> bool:
        return self.pipeline is not None

    def fit(self, texts: list[str], labels: list[str]) -> "TfidfClassifier":
        from sklearn.pipeline import FeatureUnion

        features = FeatureUnion(
            [
                ("word", self.word_vectorizer),
                ("char", self.char_vectorizer),
            ]
        )
        self.pipeline = Pipeline(
            [
                ("features", features),
                ("clf", self.classifier),
            ]
        )
        self.pipeline.fit([normalize(t) for t in texts], labels)
        return self

    def _require_fitted(self) -> Pipeline:
        if self.pipeline is None:
            raise RuntimeError("TfidfClassifier.fit must be called before predict")
        return self.pipeline

    def predict(self, text: str) -> str:
        return str(self._require_fitted().predict([normalize(text)])[0])

    def predict_many(self, texts: list[str]) -> list[str]:
        fitted = self._require_fitted()
        return [str(p) for p in fitted.predict([normalize(t) for t in texts])]

    def decision_scores(self, text: str) -> np.ndarray:
        """Raw margins per class, for confidence-gated human triage later."""
        return self._require_fitted().decision_function([normalize(text)])[0]

    @property
    def classes(self) -> list[str]:
        """Labels in the order `decision_scores` columns correspond to.

        sklearn orders classes alphabetically, which is NOT the order of
        CATEGORIES, so argmax must always be mapped through this.
        """
        return [str(c) for c in self._require_fitted().classes_]


def confidence_from_scores(scores: np.ndarray) -> float:
    """Softmax over the SVM margins, as a triage signal.

    LinearSVC has no calibrated probabilities, so this is an uncalibrated
    relative score, useful for routing low-confidence cases to a human. It is
    not a probability and must not be presented to users as one.
    """
    shifted = np.exp(scores - scores.max())
    return float(shifted.max() / shifted.sum())


class TfidfClassifierError(RuntimeError):
    """Raised when no model can be produced at all."""


def load_dataset(path: Path | None = None) -> tuple[list[str], list[str]]:
    import csv

    source = path or dataset_path()
    texts: list[str] = []
    labels: list[str] = []
    with source.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            text = row["text"].strip()
            label = row["category"].strip()
            if text and label:
                texts.append(text)
                labels.append(label)
    if not texts:
        raise TfidfClassifierError(f"no training rows found in {source}")
    return texts, labels


def train_from_dataset(path: Path | None = None) -> TfidfClassifier:
    texts, labels = load_dataset(path)
    logger.info("training baseline classifier on %d rows", len(texts))
    return TfidfClassifier().fit(texts, labels)


def save(model: TfidfClassifier, path: Path | None = None) -> Path:
    import joblib

    target = path or model_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, target)
    return target


def load(path: Path | None = None) -> TfidfClassifier:
    import joblib

    source = path or model_path()
    model = joblib.load(source)
    if not isinstance(model, TfidfClassifier) or not model.is_fitted:
        raise TfidfClassifierError(f"{source} is not a fitted TfidfClassifier")
    return model


def build_model(prefer_disk: bool = True) -> TfidfClassifier | None:
    """Return a fitted model, or None if one cannot be produced.

    Order: load the persisted artifact, else train from the labeled dataset.
    Returning None instead of raising lets the caller degrade to the rule-based
    fallback instead of taking the service down.
    """
    if prefer_disk and model_path().exists():
        try:
            return load()
        except Exception:  # noqa: BLE001 - a bad artifact must not stop boot
            logger.warning(
                "model artifact at %s could not be loaded; retraining",
                model_path(),
                exc_info=True,
            )

    try:
        return train_from_dataset()
    except Exception:  # noqa: BLE001 - degrade rather than fail startup
        logger.warning(
            "no usable training data at %s; falling back to rule-based "
            "classification",
            dataset_path(),
            exc_info=True,
        )
        return None


_INSTALLED: TfidfClassifier | None = None


def install_model(model: TfidfClassifier | None) -> None:
    """Swap the fitted model used by the module-level classify()."""
    global _INSTALLED
    _INSTALLED = model


def installed_model() -> TfidfClassifier | None:
    return _INSTALLED


def ensure_model_installed(prefer_disk: bool = True) -> TfidfClassifier | None:
    """Install a model once per process; safe to call on every startup."""
    if _INSTALLED is None:
        install_model(build_model(prefer_disk=prefer_disk))
    return _INSTALLED


def classify(text: str) -> dict:
    """Classify a need, preferring the fitted baseline over the rule fallback.

    Always returns the keys the AI service contract requires (`category`,
    `urgency_score`, `priority`) plus `classifier`, `confidence` and
    `urgency_engine` so callers and operators can see which engine answered.
    Urgency comes from the calibrated model when one is installed; otherwise
    it degrades to the keyword heuristic (see calibration.py).
    """
    model = _INSTALLED

    calibrated = calibration.calibrated_urgency(text)
    if calibrated is not None:
        urgency = calibrated
        urgency_engine = calibration.URGENCY_ENGINE
    else:
        urgency = score_urgency(text)
        urgency_engine = calibration.FALLBACK_ENGINE

    if model is None:
        result = rule_classify(text)
        return {
            **result,
            **urgency,
            "classifier": FALLBACK_ENGINE,
            "confidence": None,
            "urgency_engine": urgency_engine,
        }

    scores = model.decision_scores(text)
    category = model.classes[int(np.argmax(scores))]
    return {
        "category": category,
        **urgency,
        "classifier": MODEL_ENGINE,
        "confidence": round(confidence_from_scores(scores), 4),
        "urgency_engine": urgency_engine,
    }
