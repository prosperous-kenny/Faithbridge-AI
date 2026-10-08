"""Phase 0 evaluation harness (task 5).

Measures classification accuracy per category with a held-out split, before any
tuning, so the accuracy claims in eval/report.md are reproducible and the
Phase 0 exit gate (>=85% overall, no category below 70%) is checkable.

Split is stratified and deterministic: the same seed always yields the same
fold, so re-running the harness does not change the numbers.

Run:  python eval/evaluate.py
"""

import csv
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

AI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AI_DIR))

from build_dataset import TEMPLATE_SOURCE  # noqa: E402

from faithbridge_ai.baseline import CATEGORIES, TfidfClassifier  # noqa: E402
from faithbridge_ai.classifier import classify as rule_classify  # noqa: E402

DATASET = Path(__file__).resolve().parent / "dataset.csv"
SEED = 42
TEST_FRACTION = 0.3


def load_rows(path: Path = DATASET) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            text = row["text"].strip()
            label = row["category"].strip()
            if text and label:
                rows.append(
                    {
                        "text": text,
                        "category": label,
                        "source": (row.get("source") or "unlabeled").strip(),
                    }
                )
    return rows


def load_dataset(path: Path = DATASET) -> tuple[list[str], list[str]]:
    rows = load_rows(path)
    return [r["text"] for r in rows], [r["category"] for r in rows]


def provenance(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["source"]] = counts.get(row["source"], 0) + 1
    return counts


def render_provenance(rows: list[dict]) -> list[str]:
    counts = provenance(rows)
    lines = [f"dataset: {len(rows)} rows", "provenance:"]
    for source, count in sorted(counts.items()):
        lines.append(f"  {source:<16} {count}")
    if set(counts) <= {TEMPLATE_SOURCE}:
        lines.append(
            "WARNING: every row is template-generated. This measures fit to the "
            "template"
        )
        lines.append(
            "  library, not field accuracy. PRD §23 requires real submissions "
            "before the"
        )
        lines.append("  launch gate can be claimed as met.")
    return lines



def split(texts: list[str], labels: list[str]) -> tuple:
    return train_test_split(
        texts,
        labels,
        test_size=TEST_FRACTION,
        random_state=SEED,
        stratify=labels,
    )


def evaluate_model(name: str, predict) -> dict:
    texts, labels = load_dataset()
    x_train, x_test, y_train, y_test = split(texts, labels)

    if predict == "tfidf":
        model = TfidfClassifier().fit(x_train, y_train)
        predictions = model.predict_many(x_test)
    else:
        predictions = [rule_classify(t)["category"] for t in x_test]

    return {
        "name": name,
        "accuracy": accuracy_score(y_test, predictions),
        "report": classification_report(
            y_test, predictions, labels=CATEGORIES, output_dict=True, zero_division=0
        ),
        "confusion": confusion_matrix(y_test, predictions, labels=CATEGORIES),
        "x_test": x_test,
        "y_test": y_test,
        "predictions": predictions,
        "train_size": len(x_train),
        "test_size": len(x_test),
    }


def render(result: dict) -> str:
    lines = [
        f"=== {result['name']} ===",
        f"train {result['train_size']} / test {result['test_size']}",
        f"overall accuracy: {result['accuracy']:.3f}",
        "",
        "per-category (support / precision / recall / f1):",
    ]
    report = result["report"]
    for category in CATEGORIES:
        stats = report.get(category, {})
        lines.append(
            f"  {category:<12} support={int(stats.get('support', 0)):>3}  "
            f"precision={stats.get('precision', 0.0):.3f}  "
            f"recall={stats.get('recall', 0.0):.3f}  "
            f"f1={stats.get('f1-score', 0.0):.3f}"
        )
    lines.append("")
    lines.append("confusion matrix (rows = true, cols = predicted):")
    header = "                " + " ".join(f"{c[:6]:>6}" for c in CATEGORIES)
    lines.append(header)
    for category, row in zip(CATEGORIES, result["confusion"], strict=True):
        lines.append(
            f"  {category:<12} " + " ".join(f"{int(v):>6}" for v in row)
        )
    return "\n".join(lines)


def gate_check(result: dict, threshold: float = 0.85, floor: float = 0.70) -> list[str]:
    """Return a list of unmet gate criteria; empty means the gate passed."""
    failures: list[str] = []
    if result["accuracy"] < threshold:
        failures.append(
            f"overall accuracy {result['accuracy']:.3f} < {threshold:.2f}"
        )
    for category in CATEGORIES:
        stats = result["report"].get(category, {})
        for metric in ("precision", "recall"):
            value = stats.get(metric, 0.0)
            if value < floor:
                failures.append(
                    f"{category} {metric} {value:.3f} < {floor:.2f}"
                )
    return failures


def misclassified(result: dict, limit: int = 12) -> list[tuple[str, str, str]]:
    out = []
    for text, truth, pred in zip(
        result["x_test"], result["y_test"], result["predictions"], strict=True
    ):
        if truth != pred:
            out.append((text, truth, pred))
    return out[:limit]


def write_results(text: str) -> None:
    """Persist results.txt with fixed encoding and LF endings.

    CI diffs this file against a fresh run, so the bytes must not vary by
    platform: UTF-8 without BOM, LF only.
    """
    Path(__file__).resolve().parent.joinpath("results.txt").write_text(
        text.replace("\r\n", "\n"), encoding="utf-8", newline="\n"
    )


def main() -> int:
    np.random.seed(SEED)

    rows = load_rows()
    tfidf = evaluate_model("TF-IDF + LinearSVC", "tfidf")
    rules = evaluate_model("Rule-based keywords (current)", "rules")

    for line in render_provenance(rows):
        print(line)
    print()
    print(render(tfidf))
    print()
    print(render(rules))
    print()

    for result in (tfidf, rules):
        failures = gate_check(result)
        status = "PASS" if not failures else "FAIL"
        print(f"Phase 0 gate ({result['name']}): {status}")
        for failure in failures:
            print(f"  - {failure}")

    print()
    print("sample misclassifications (TF-IDF + LinearSVC):")
    for text, truth, pred in misclassified(tfidf):
        print(f"  [{truth} -> {pred}] {text}")

    return 0


def run_and_write() -> int:
    """Run the harness and persist the full report to results.txt."""
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main()
    text = buffer.getvalue()
    print(text, end="")
    write_results(text)
    return code


if __name__ == "__main__":
    sys.exit(run_and_write())
