"""Generate labeled urgency data for Phase 2 calibration.

Phase 0 scored urgency with keyword heuristics and fixed 40/60/80 bands. This
generator authors the labeled examples that let Phase 2 calibrate urgency
against data instead of assumptions: each template carries an urgency score in
one of the four priority bands, so a model can learn the phrasing that
separates "could use help eventually" from "our home burned down tonight".

Templates deliberately reuse words across bands (rent, food, help, school,
week appear at every severity) so no single keyword can game the calibration:
the model must separate bands from combination *context* -- e.g. "some time
next month" vs "is due today". Writing them as full sentences, like the
category templates, keeps them readable as real submissions rather than as
keyword lists.

Like the category set, every row is synthetic (source ``urgency-template-v1``):
it measures fit to the template style, not field accuracy. The harness prints
that warning on every run.

Scores are chosen to span their band rather than hug a boundary, so each row
carries genuine within-band variation.

Run:  python eval/build_urgency_dataset.py
"""

import csv
from pathlib import Path

URGENCY_SOURCE = "urgency-template-v1"

BAND_ORDER = ["low", "medium", "high", "critical"]

# band -> list of (template, score) pairs. {n} is a household size.
TEMPLATES: dict[str, list[tuple[str, int]]] = {
    "low": [
        ("We could use some help arranging transport to a job interview next month", 22),
        ("I would appreciate guidance on budgeting for our household of {n}", 26),
        ("We might need help with school supplies later in the term", 30),
        ("I want to explore support options for paying down our electricity bill slowly", 34),
        ("Our family could use advice on affordable housing in the area", 38),
        ("I am hoping to find a training course to improve my CV sometime soon", 24),
        ("We are planning for next term and would like information on available programs", 28),
        ("I would like help understanding how to apply for assistance forms", 32),
        ("I am comparing options for food support in case we need it this winter", 23),
        ("We might look for help with a deposit if we decide to move next year", 27),
        ("I want to ask about the rent support scheme that a friend mentioned", 31),
        ("Our children may need uniforms when the fee schedule changes later", 35),
        ("I would like to know what documentation a housing application needs", 39),
        ("We are thinking about how to manage school costs for the longer term", 25),
        ("I want advice on saving for medicine in case our situation stays as is", 29),
        ("We may need support with utilities after the cold season arrives", 33),
        ("I am researching employment programs for when my contract ends", 37),
        ("Our family could use a referral to a financial planning group", 21),
        ("I would like details on requirements before we apply for anything", 36),
        ("We hope to find help with a small project at the parish later", 30),
    ],
    "medium": [
        ("We need some help with groceries before the end of the month", 42),
        ("I need support paying for transport to keep my job", 46),
        ("Our children need uniforms before school starts next week", 50),
        ("We are looking for help with paying a portion of this month's rent", 54),
        ("I need assistance covering the cost of a clinic visit", 58),
        ("We could use help buying food for the coming fortnight", 44),
        ("I need help with the application costs for a training program", 48),
        ("Our household needs support with utilities while we look for work", 52),
        ("We need help covering the bus fare to get to our appointment", 43),
        ("I need support with the fee for a certification I am applying for", 47),
        ("Our family needs help replacing a few school books that are worn out", 51),
        ("We are hoping for assistance with the deposit on a modest apartment", 55),
        ("I need help with a small portion of the payment for my clinic tests", 59),
        ("We could use help with the basic groceries for the next couple of weeks", 45),
        ("I need assistance to register for a course starting soon", 49),
        ("Our household needs support with the heating bill this month", 53),
        ("We need help with the cost of a repair so we can keep working", 57),
        ("I need support with the fees for my children's day care", 41),
        ("Our family needs help with a few expenses while my wages reset", 56),
        ("We are asking for assistance with groceries for the coming weeks", 44),
    ],
    "high": [
        ("I lost my job and cannot pay the rent that is due this week", 62),
        ("We are behind on bills and our water service may be cut off any day", 66),
        ("I need help with medicine my doctor says I cannot stop taking", 70),
        ("Our family is running out of food and payday is two weeks away", 74),
        ("I cannot afford the hospital fees for treatment that starts this week", 78),
        ("We are being asked to leave our home soon and need rent help now", 64),
        ("My child's school fees are unpaid and she is being sent home", 68),
        ("We have no money left for food and the fridge is empty tonight", 72),
        ("Our rent is overdue and the landlord says pay or move out", 63),
        ("I cannot buy the medication and my supply runs out within days", 67),
        ("We are behind on our utility bill and the account may be closed", 71),
        ("My wages stopped and there is no money for food this week", 75),
        ("The clinic says I must start treatment soon and we cannot pay", 79),
        ("We are at risk of losing the apartment without help this month", 65),
        ("My school fees are overdue and I cannot register for the term", 69),
        ("We have no income left and the cupboard is nearly empty", 73),
        ("I cannot afford the repair and without it I cannot get to work", 61),
        ("Our family is short on rent and the notice is already here", 64),
        ("We need money for food before the savings fully run out", 76),
        ("I am behind on the clinic bill and my care may be paused", 77),
    ],
    "critical": [
        ("We are being evicted tomorrow and need emergency housing tonight", 82),
        ("Our house caught fire and we have nowhere to sleep tonight", 86),
        ("I need urgent surgery and cannot pay unless we get help today", 90),
        ("There is no food and no money and our children have not eaten for two days", 94),
        ("A flood destroyed our home and we need emergency relief immediately", 98),
        ("We are homeless from tonight and need shelter for the family right away", 84),
        ("My father needs urgent dialysis and we cannot afford it", 88),
        ("The landlord is locking us out asap unless we pay everything now", 92),
        ("Our home is uninhabitable right now and we need a place to stay tonight", 83),
        ("I need emergency help today, our gas has been shut off with a baby inside", 87),
        ("We have no food tonight and no money until an unknown date", 91),
        ("A sudden medical emergency today means we need help with the bill now", 95),
        ("Our building is flooding now and we need to leave immediately", 99),
        ("The eviction is happening this morning and we need urgent assistance", 85),
        ("We lost everything in the fire and need help with shelter tonight", 89),
        ("I need critical support right now, my medication cannot wait until tomorrow", 93),
        ("Our family has nowhere to sleep tonight after the storm", 81),
        ("We are being turned out of the house today and need help at once", 96),
        ("A disaster left us with nothing and we need emergency support this hour", 100),
        ("My child is in danger tonight and we need immediate shelter", 90),
    ],
}


def build_rows() -> list[tuple[str, int, str, str]]:
    """(text, urgency_score, band, source) rows, deterministic."""
    rows: list[tuple[str, int, str, str]] = []
    sizes = [2, 3, 4, 5, 6]
    for band in BAND_ORDER:
        templates = TEMPLATES[band]
        for index, (template, score) in enumerate(templates):
            size = sizes[index % len(sizes)]
            rows.append((template.format(n=size), score, band, URGENCY_SOURCE))
    return rows


def main() -> None:
    rows = build_rows()
    out_path = Path(__file__).resolve().parent / "urgency_dataset.csv"

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["text", "urgency_score", "band", "source"])
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for _, _score, band, _ in rows:
        counts[band] = counts.get(band, 0) + 1
    print(f"wrote {len(rows)} rows to {out_path}")
    for band in BAND_ORDER:
        print(f"  {band:<10} {counts.get(band, 0)}")


if __name__ == "__main__":
    main()