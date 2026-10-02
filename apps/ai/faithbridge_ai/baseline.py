"""Phase 0 classifier baseline behind one interface (task 4).

The rule-based keyword matcher in classifier.py stays available so the eval
harness can compare against it, but TF-IDF + linear SVM is the candidate
baseline. Sentence-transformers is deliberately not wired in yet: it needs a
torch download at runtime, which is too heavy to make the default path. The
comparison and the decision are recorded in eval/report.md and
docs/adr/0001-model-selection.md.
"""

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

CATEGORIES = ["food", "housing", "medical", "education", "employment", "emergency"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


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
        self._is_fitted = False

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
        self._is_fitted = True
        return self

    def predict(self, text: str) -> str:
        if not self._is_fitted:
            raise RuntimeError("TfidfClassifier.fit must be called before predict")
        return str(self.pipeline.predict([normalize(text)])[0])

    def predict_many(self, texts: list[str]) -> list[str]:
        if not self._is_fitted:
            raise RuntimeError("TfidfClassifier.fit must be called before predict")
        return [str(p) for p in self.pipeline.predict([normalize(t) for t in texts])]

    def decision_scores(self, text: str) -> np.ndarray:
        """Raw margins per class, for confidence-gated human triage later."""
        if not self._is_fitted:
            raise RuntimeError("TfidfClassifier.fit must be called before decision_scores")
        return self.pipeline.decision_function([normalize(text)])[0]


def classify(text: str) -> dict:
    """Module-level entrypoint mirroring classifier.classify's shape.

    Uses the rule-based matcher so behaviour is unchanged until a fitted model
    is installed via install_model(); keeps the AI service contract stable.
    """
    from faithbridge_ai.classifier import classify as rule_classify

    return rule_classify(text)


_INSTALLED: TfidfClassifier | None = None


def install_model(model: TfidfClassifier) -> None:
    """Swap in a fitted model for the module-level classify()."""
    global _INSTALLED
    _INSTALLED = model
