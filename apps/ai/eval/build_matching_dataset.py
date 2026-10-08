"""Generate labeled donor-program matching data for the Phase 3 gate.

PRD Use Case 2: a donor indicates budget, preferred causes and location, and
FaithBridge recommends programs that match. The match certifier is "top-3 match
precision >= 70% on a hand-labelled sample", which needs a labelled dataset:
a fixed program pool, a set of donor profiles, and -- for each profile -- the
three programs a careful human would recommend first.

Labels are synthetic (source ``matching-template-v1``), written by a human
against the pool below *before* the ranker was tuned, following the same rule
the product uses: cause first, then budget fit, then location. Like the
category and urgency sets, this measures fit to the template library, not
field accuracy, and the harness prints that warning on every run.

Empty ``causes`` means "any cause" (the donor has no preference); the label
then picks the best all-round programs for the stated budget and location.

Run:  python eval/build_matching_dataset.py
"""

import csv
from pathlib import Path

MATCHING_SOURCE = "matching-template-v1"

# (program_id, name, category, description, location, budget_needed,
#  organization_name). Six causes, three programs each: wide enough that a
# single-cause donor still forces a real ranking among three candidates.
POOL: list[tuple[int, str, str, str, str, int, str]] = [
    (
        1, "Food Bank", "food",
        "Weekly groceries and hot meals for families in food distress",
        "Lagos", 400, "Grace Community Church",
    ),
    (
        2, "Community Kitchen", "food",
        "Communal meals and take-home food packs for low-income households",
        "Accra", 300, "Hope Food Bank",
    ),
    (
        3, "Food Voucher Scheme", "food",
        "Cash vouchers redeemable at partner stores for household groceries",
        "Lagos", 600, "Grace Community Church",
    ),
    (
        4, "Rent Support Fund", "housing",
        "Direct rent assistance for households facing eviction",
        "Lagos", 800, "Grace Community Church",
    ),
    (
        5, "Emergency Shelter", "housing",
        "Short-term and transitional shelter for displaced families",
        "Accra", 1000, "Hope Food Bank",
    ),
    (
        6, "Housing Stabilization", "housing",
        "Deposit help and rent arrears clearance to stop families losing their home",
        "Lagos", 450, "Grace Community Church",
    ),
    (
        7, "Clinic Subsidy", "medical",
        "Subsidised clinic visits and consultations for uninsured families",
        "Lagos", 500, "Grace Community Church",
    ),
    (
        8, "Medicine Access Fund", "medical",
        "Co-payment support for chronic prescriptions and life-saving drugs",
        "Accra", 300, "Hope Food Bank",
    ),
    (
        9, "Maternity Care Fund", "medical",
        "Prenatal and delivery care costs for mothers without insurance",
        "Lagos", 700, "Grace Community Church",
    ),
    (
        10, "School Fees Fund", "education",
        "Termly school fees for primary and secondary students",
        "Lagos", 400, "Grace Community Church",
    ),
    (
        11, "Scholarship Program", "education",
        "Merit and need scholarships covering tuition and study materials",
        "Accra", 900, "Hope Food Bank",
    ),
    (
        12, "Learning Materials Fund", "education",
        "Textbooks, uniforms and school supplies for children in need",
        "Lagos", 250, "Grace Community Church",
    ),
    (
        13, "Job Training Center", "employment",
        "Skills training, certifications and job placement support",
        "Lagos", 600, "Grace Community Church",
    ),
    (
        14, "Employment Readiness", "employment",
        "Interview coaching, CV workshops and job matching services",
        "Accra", 350, "Hope Food Bank",
    ),
    (
        15, "Micro-Grant Program", "employment",
        "Startup microloans and small grants for informal traders",
        "Lagos", 1000, "Grace Community Church",
    ),
    (
        16, "Emergency Relief Fund", "emergency",
        "Immediate relief for families hit by fire, flood or disaster",
        "Accra", 1200, "Hope Food Bank",
    ),
    (
        17, "Disaster Response Team", "emergency",
        "Rapid on-the-ground response and shelter support for disaster victims",
        "Lagos", 500, "Grace Community Church",
    ),
    (
        18, "Crisis Housing Blitz", "emergency",
        "Emergency accommodation and cleanup crews after storms displace families",
        "Accra", 600, "Hope Food Bank",
    ),
]

PROGRAM_IDS = {program[0] for program in POOL}

# donor_id, causes (comma-separated), budget, location, expected_program_ids.
PROFILES: list[tuple[int, str, float, str, str]] = [
    (1, "food", 500, "Lagos", "1,3,2"),
    (2, "food", 300, "Lagos", "1,3,2"),
    (3, "food", 600, "Accra", "2,1,3"),
    (4, "housing", 900, "Lagos", "4,6,5"),
    (5, "housing", 500, "Accra", "6,4,5"),
    (6, "medical", 2000, "Lagos", "7,9,8"),
    (7, "medical", 400, "Accra", "8,9,7"),
    (8, "education", 1000, "Lagos", "10,12,11"),
    (9, "employment", 500, "Accra", "14,13,15"),
    (10, "emergency", 2000, "Lagos", "17,18,16"),
    (11, "food,medical", 500, "Lagos", "1,3,7"),
    (12, "housing,emergency", 1000, "Lagos", "4,6,17"),
    (13, "education,employment", 2000, "Accra", "11,14,10"),
    # Empty causes means "any cause"; the label is the best all-round Lagos
    # programs within the stated budget (clinic subsidy, job training and
    # rapid disaster response are all plausible first picks for a $700 donor).
    (14, "", 700, "Lagos", "7,13,17"),
    (15, "medical,emergency", 300, "Accra", "8,18,16"),
]


def build_rows() -> list[tuple[int, str, float, str, str, str]]:
    """(donor_id, causes, budget, location, expected_program_ids, source) rows."""
    rows: list[tuple[int, str, float, str, str, str]] = []
    for donor_id, causes, budget, location, expected in PROFILES:
        rows.append(
            (donor_id, causes, float(budget), location, expected, MATCHING_SOURCE)
        )
    return rows


def main() -> None:
    rows = build_rows()
    out_path = Path(__file__).resolve().parent / "matching_dataset.csv"

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["donor_id", "causes", "budget", "location", "expected_program_ids", "source"]
        )
        writer.writerows(rows)

    print(f"wrote {len(rows)} donor profiles to {out_path}")
    print(f"program pool: {len(POOL)} programs across "
          f"{sorted({program[2] for program in POOL})}")


if __name__ == "__main__":
    main()