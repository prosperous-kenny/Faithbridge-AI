"""Phase 3 donor-matching evaluation harness.

Measures the top-3 match precision gate from the implementation plan: for each
hand-labelled donor profile, how many of the three best programs the ranker
actually puts in its top three. The ranking contract is "top-3 match precision
>= 70% on a hand-labelled sample"; getting the right *three* is what a donor
sees on screen, so precision@3 (membership, not order) is the checkable gate.

Run:  python eval/evaluate_matching.py
"""

import csv
import sys
from pathlib import Path

AI_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AI_DIR))
sys.path.insert(0, str(EVAL_DIR))


from build_matching_dataset import POOL  # noqa: E402

from faithbridge_ai.matching import Program, rank_matches  # noqa: E402

DATASET = EVAL_DIR / "matching_dataset.csv"

# The pool is part of the committed data, not of the request path: the API
# supplies its active programs at call time, the harness supplies these.
PROGRAMS = [
    Program(
        program_id=program_id,
        name=name,
        category=category,
        description=description,
        location=location,
        budget_needed=budget_needed,
        organization_name=organization_name,
    )
    for program_id, name, category, description, location, budget_needed, organization_name in POOL
]


def load_rows(path: Path = DATASET) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            donor_id = row["donor_id"].strip()
            causes = row["causes"].strip()
            budget = row["budget"].strip()
            location = row["location"].strip()
            expected = row["expected_program_ids"].strip()
            if not donor_id:
                continue
            rows.append(
                {
                    "donor_id": int(donor_id),
                    "causes": [c for c in causes.split(",") if c] if causes else [],
                    "budget": float(budget) if budget else 0.0,
                    "location": location or None,
                    "expected": [int(p) for p in expected.split(",") if p],
                    "source": (row.get("source") or "unlabeled").strip(),
                }
            )
    return rows


def evaluate_matching() -> dict:
    rows = load_rows()
    per_donor: list[dict] = []
    for row in rows:
        ranked = rank_matches(
            causes=row["causes"],
            budget=row["budget"],
            location=row["location"],
            programs=PROGRAMS,
            top_k=3,
        )
        predicted = {result.program_id for result in ranked}
        expected = set(row["expected"])
        hits = len(predicted & expected)
        per_donor.append(
            {
                "donor_id": row["donor_id"],
                "causes": row["causes"],
                "expected": sorted(expected),
                "predicted": sorted(predicted),
                "hits": hits,
                "precision": hits / len(expected),
            }
        )
    return {"rows": len(per_donor), "per_donor": per_donor}


def render(result: dict) -> str:
    total = sum(row["precision"] for row in result["per_donor"])
    mean = total / result["rows"]
    lines = [
        "=== Donor-program matching (TF-IDF sparse embedding + constraints) ===",
        f"donor profiles: {result['rows']}",
        f"top-3 match precision: {mean:.3f}",
        "",
        "per-donor (donor_id / causes / precision / expected / predicted):",
    ]
    for row in sorted(result["per_donor"], key=lambda r: r["donor_id"]):
        causes = ",".join(row["causes"]) or "(all)"
        lines.append(
            f"  #{row['donor_id']:<3} {causes:<12} {row['precision']:.2f}  "
            f"e={row['expected']}  p={row['predicted']}"
        )
    lines.append("")
    lines.append(
        "WARNING: matching data is template-generated. Labels were written by a "
        "human against a"
    )
    lines.append(
        "  fixed synthetic pool before tuning; this measures fit to that "
        "library, not field"
    )
    lines.append(
        "  quality. Real donor behaviour and real program inventories are PRD "
        "requirement 23."
    )
    return "\n".join(lines)


def gate_check(result: dict, *, min_top3: float = 0.70) -> list[str]:
    failures: list[str] = []
    total = sum(row["precision"] for row in result["per_donor"])
    mean = total / result["rows"]
    if mean < min_top3:
        failures.append(f"top-3 precision {mean:.3f} < {min_top3:.2f}")
    for row in result["per_donor"]:
        if row["precision"] < 1.0 / len(row["expected"]):
            failures.append(
                f"donor #{row['donor_id']} found none of its {len(row['expected'])} "
                f"expected programs in the top three"
            )
    return failures


def write_results(text: str) -> None:
    Path(__file__).resolve().parent.joinpath("matching_results.txt").write_text(
        text.replace("\r\n", "\n"), encoding="utf-8", newline="\n"
    )


def main() -> int:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rows = load_rows()
        result = evaluate_matching()

        print("dataset:", len(rows), "profiles  provenance:",
              {r["source"] for r in rows})
        print()
        print(render(result))
        print()
        failures = gate_check(result, min_top3=0.70)
        print(f"matching gate: {'PASS' if not failures else 'FAIL'}")
        for failure in failures:
            print(f"  - {failure}")

    text = buffer.getvalue()
    print(text, end="")
    write_results(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())