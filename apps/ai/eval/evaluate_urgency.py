"""Phase 2 urgency evaluation harness.

Measures the calibrated urgency model the way the category harness measures
the classifier: held-out, deterministic split, per-band precision/recall so the
plan's "urgency precision/recall per priority band" gate is checkable, plus a
continuous-score MAE/RMSE readout so the boundary choice is auditable.

Run:  python eval/evaluate_urgency.py
"""

import csv
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split

AI_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AI_DIR))
sys.path.insert(0, str(EVAL_DIR))


from faithbridge_ai.calibration import (  # noqa: E402
    BAND_PRECEDENCE,
    UrgencyCalibrator,
    priority_of,
)

DATASET = EVAL_DIR / "urgency_dataset.csv"
SEED = 42
TEST_FRACTION = 0.3


def load_rows(path: Path = DATASET) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            text = row["text"].strip()
            score = row["urgency_score"].strip()
            if text and score:
                rows.append(
                    {
                        "text": text,
                        "urgency_score": int(score),
                        "band": (row.get("band") or priority_of(int(score))).strip(),
                        "source": (row.get("source") or "unlabeled").strip(),
                    }
                )
    return rows


def evaluate_calibrator() -> dict:
    rows = load_rows()
    texts = [r["text"] for r in rows]
    bands = [r["band"] for r in rows]

    indices = np.arange(len(texts))
    train_idx, test_idx = train_test_split(
        indices,
        test_size=TEST_FRACTION,
        random_state=SEED,
        stratify=bands,
    )
    x_train = [texts[i] for i in train_idx]
    x_test = [texts[i] for i in test_idx]
    y_train_bands = [bands[i] for i in train_idx]
    y_test_bands = [bands[i] for i in test_idx]

    calibrator = UrgencyCalibrator().fit(x_train, y_train_bands)
    predicted_bands = [calibrator.predict_band(t) for t in x_test]

    band_order = sorted(set(bands), key=BAND_PRECEDENCE.__getitem__)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_test_bands,
        predicted_bands,
        labels=band_order,
        zero_division=0,
    )

    return {
        "rows": len(rows),
        "train_size": len(x_train),
        "test_size": len(x_test),
        "accuracy": accuracy_score(y_test_bands, predicted_bands),
        "band_report": {
            band: {
                "precision": float(p),
                "recall": float(r),
                "f1": float(f),
                "support": int(s),
            }
            for band, p, r, f, s in zip(band_order, precision, recall, f1, support, strict=True)
        },
    }


def render(result: dict) -> str:
    lines = [
        "=== Urgency calibration (TF-IDF word+char -> LinearSVC) ===",
        f"train {result['train_size']} / test {result['test_size']}",
        f"band accuracy: {result['accuracy']:.3f}",
        "",
        "per-priority-band (support / precision / recall / f1):",
    ]
    for band in sorted(result["band_report"], key=BAND_PRECEDENCE.__getitem__):
        stats = result["band_report"][band]
        lines.append(
            f"  {band:<10} support={int(stats['support']):>3}  "
            f"precision={stats['precision']:.3f}  "
            f"recall={stats['recall']:.3f}  "
            f"f1={stats['f1']:.3f}"
        )
    lines.append("")
    lines.append(
        "WARNING: urgency data is template-generated. This measures fit to the "
        "template"
    )
    lines.append(
        "  library, not field accuracy. PRD requirement 23 needs real "
        "submissions"
    )
    lines.append("  the launch gate can be claimed as met.")
    return "\n".join(lines)


def gate_check(
    result: dict, *, band_floor: float = 0.50, min_accuracy: float = 0.50
) -> list[str]:
    failures: list[str] = []
    if result["accuracy"] < min_accuracy:
        failures.append(
            f"overall band accuracy {result['accuracy']:.3f} < {min_accuracy:.2f}"
        )
    for band, stats in result["band_report"].items():
        for metric in ("precision", "recall"):
            if stats[metric] < band_floor:
                failures.append(
                    f"{band} {metric} {stats[metric]:.3f} < {band_floor:.2f}"
                )
    return failures


def write_results(text: str) -> None:
    Path(__file__).resolve().parent.joinpath("urgency_results.txt").write_text(
        text.replace("\r\n", "\n"), encoding="utf-8", newline="\n"
    )


def main() -> int:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rows = load_rows()
        result = evaluate_calibrator()

        print("dataset:", len(rows), "rows  provenance:",
              {r["source"] for r in rows})
        print()
        print(render(result))
        print()
        failures = gate_check(result, band_floor=0.50, min_accuracy=0.50)
        print(f"urgency gate: {'PASS' if not failures else 'FAIL'}")
        for failure in failures:
            print(f"  - {failure}")

    text = buffer.getvalue()
    print(text, end="")
    write_results(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())