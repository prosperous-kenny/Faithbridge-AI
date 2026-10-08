"""Urgency calibration: a model replaces the keyword heuristic's fixed bands.

Phase 0 urgency came from ``score_urgency`` keyword rules with hard-coded
40/60/80 thresholds. That is fragile and unverifiable against any labeled
truth. Phase 2 replaces it with a model trained on hand-labeled urgency bands
(eval/urgency_dataset.csv): a TF-IDF (word + char) -> LinearSVC classifier over
the four priority bands, with the reported score being the calibrated band
centre.

Priority is therefore *calibrated*: it comes from a model fit on labeled
examples, not from assumed cutoffs. Mirrors baseline.py's swap-ability contract
- classification of category stays owned by TfidfClassifier, urgency by
UrgencyCalibrator, each degrading to its heuristic fallback independently. The
`urgency_engine` reported by the AI service records which one answered.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

logger = logging.getLogger(__name__)

BAND_ORDER = ["critical", "high", "medium", "low"]
BAND_PRECEDENCE = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# The score a caller receives for a predicted band is this calibrated centre.
# Bands, not raw scores, are what the model learns: with few labeled examples,
# four coarse classes are estimable where a continuous score is not.
BAND_CENTRES = {"critical": 90, "high": 70, "medium": 50, "low": 30}

URGENCY_ENGINE = "tfidf-svc-calibrated"
FALLBACK_ENGINE = "rules-keyword-fallback"

AI_DIR = Path(__file__).resolve().parent.parent
DEFAULT_URGENCY_MODEL_PATH = AI_DIR / "models" / "urgency_calibration.joblib"
DEFAULT_URGENCY_DATASET_PATH = AI_DIR / "eval" / "urgency_dataset.csv"


def model_path() -> Path:
    return Path(os.getenv("FAITHBRIDGE_URGENCY_MODEL_PATH", DEFAULT_URGENCY_MODEL_PATH))


def dataset_path() -> Path:
    return Path(
        os.getenv("FAITHBRIDGE_URGENCY_DATA", DEFAULT_URGENCY_DATASET_PATH)
    )


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def priority_of(score: int) -> str:
    """Inverse map: score -> band, for labelling rows that carry no band column."""
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


class UrgencyCalibrator:
    """TF-IDF (word 1-2 grams + char 3-5 grams) into a linear SVM over bands.

    The feature mix mirrors TfidfClassifier because misspelled and abbreviated
    beneficiary text benefits from character n-grams there; urgency phrasing
    ("tonight", "asap") benefits from the same robustness here.
    """

    def __init__(self) -> None:
        self.word_vectorizer = TfidfVectorizer(
            ngram_range=(1, 3),
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

    def fit(self, texts: list[str], bands: list[str]) -> UrgencyCalibrator:
        self.pipeline = Pipeline(
            [
                (
                    "features",
                    FeatureUnion(
                        [
                            ("word", self.word_vectorizer),
                            ("char", self.char_vectorizer),
                        ]
                    ),
                ),
                ("clf", self.classifier),
            ]
        )
        self.pipeline.fit([normalize(t) for t in texts], bands)
        return self

    def _require_fitted(self) -> Pipeline:
        if self.pipeline is None:
            raise RuntimeError("UrgencyCalibrator.fit must be called before predict")
        return self.pipeline

    def predict_band(self, text: str) -> str:
        return str(self._require_fitted().predict([normalize(text)])[0])

    def predict(self, text: str) -> dict:
        band = self.predict_band(text)
        return {"urgency_score": int(BAND_CENTRES[band]), "priority": band}


class UrgencyError(RuntimeError):
    """Raised when no calibrated model can be produced at all."""


def load_urgency_dataset(path: Path | None = None) -> tuple[list[str], list[str]]:
    """Return (texts, bands). A missing band column is inferred from the score."""
    import csv

    source = path or dataset_path()
    texts: list[str] = []
    bands: list[str] = []
    with source.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            text = row["text"].strip()
            score = row["urgency_score"].strip()
            if text and score:
                texts.append(text)
                band = (row.get("band") or "").strip() or priority_of(int(score))
                bands.append(band)
    if not texts:
        raise UrgencyError(f"no urgency rows found in {source}")
    return texts, bands


def train_from_dataset(path: Path | None = None) -> UrgencyCalibrator:
    texts, bands = load_urgency_dataset(path)
    logger.info("training urgency calibrator on %d rows", len(texts))
    return UrgencyCalibrator().fit(texts, bands)


def save_calibrator(model: UrgencyCalibrator, path: Path | None = None) -> Path:
    target = path or model_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, target)
    return target


def load_calibrator(path: Path | None = None) -> UrgencyCalibrator:
    source = path or model_path()
    model = joblib.load(source)
    if not isinstance(model, UrgencyCalibrator) or not model.is_fitted:
        raise UrgencyError(f"{source} is not a fitted UrgencyCalibrator")
    return model


def build_calibrator(prefer_disk: bool = True) -> UrgencyCalibrator | None:
    """Return a fitted calibrator, or None to keep the keyword fallback."""
    if prefer_disk and model_path().exists():
        try:
            return load_calibrator()
        except Exception:  # noqa: BLE001 - a bad artifact must not stop boot
            logger.warning(
                "urgency artifact at %s could not be loaded; retraining",
                model_path(),
                exc_info=True,
            )
    try:
        return train_from_dataset()
    except Exception:  # noqa: BLE001 - degrade rather than fail startup
        logger.warning(
            "no usable urgency data at %s; keeping the keyword heuristic",
            dataset_path(),
            exc_info=True,
        )
        return None


_INSTALLED: UrgencyCalibrator | None = None


def install_calibrator(model: UrgencyCalibrator | None) -> None:
    global _INSTALLED
    _INSTALLED = model


def installed_calibrator() -> UrgencyCalibrator | None:
    return _INSTALLED


def ensure_calibrator_installed(prefer_disk: bool = True) -> UrgencyCalibrator | None:
    if _INSTALLED is None:
        install_calibrator(build_calibrator(prefer_disk=prefer_disk))
    return _INSTALLED


def calibrated_urgency(text: str) -> dict | None:
    """Calibrated urgency, or None when no calibrator is serving."""
    model = installed_calibrator()
    if model is None:
        return None
    return model.predict(text)