"""Phase 3 donor–program matching.

Replaces the Phase 0 ``_rank`` stub (a hard-coded five-program pool scored by
keyword overlap) with a data-driven ranker. A donor's preferences (causes,
budget, location — PRD Use Case 2) are combined with the programs the API
sends in, and every program is scored as a blend of:

- **cause fit** — whether the program's category is among the donor's selected
  causes. This is the primary preference, so it doubles as a constraint: a
  program whose cause the donor did not pick is not considered a candidate at
  all (the API's pool is the universe, and this module narrows it).
- **semantic similarity** — cosine over sparse TF-IDF embeddings between the
  donor's interest text (causes, budget, location) and the program's own text
  (name, category, description, location). This is the same feature family the
  Phase 0/2 classifier and calibrator train on.
- **budget and location factors** — soft, never exclusions: a donor may fund
  part of a larger program or support a nearby community whose stated location
  does not textually match, so the returned reason tells the truth about each.

Dense sentence-transformer embeddings stay deferred exactly as ADR 0001
deferred them for the classifier: they need a ~2GB torch download that is too
heavy for the default path and for CI, and there is not yet enough real
donation data to justify it. This ranker is deterministic, dependency-light
(sklearn only) and testable; the swap target is recorded in docs/adr.

Contract notes: this module never touches a database and never sees beneficiary
rows. The API sends programs (``id``, ``name``, ``category``, ``description``,
``location``, ``budget_needed``, ``organization_name``) plus the donor's
preferences, and receives a ranked list of ``MatchResult`` objects. PII
handling (PRD §22) is the API's responsibility, exercised around this service.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer

from faithbridge_ai.baseline import CATEGORIES, normalize

ENGINE = "tfidf-sparse-embedding"

# PRD §8 category display labels for the reason strings.
CAUSE_LABELS = {
    "food": "Food Assistance",
    "education": "Education Support",
    "medical": "Medical Assistance",
    "employment": "Employment Support",
    "housing": "Housing Support",
    "emergency": "Emergency Relief",
}

# Words that make a donor cause searchable against program descriptions. Kept
# deliberately small; the category token itself is always present in a program
# document, which is what gives the strongest signal.
CAUSE_SYNONYMS = {
    "food": "food hunger groceries meals nutrition",
    "education": "education school fees tuition scholarship students",
    "medical": "medical health clinic hospital treatment medicine",
    "employment": "employment job work training skills income",
    "housing": "housing rent shelter home accommodation eviction",
    "emergency": "emergency disaster relief crisis urgent flood fire",
}

_SUPPORTED_CAUSES = frozenset(CATEGORIES)

# Blend weights for the final score. Similarity dominates; budget and location
# are tie-breakers that reward the preferences the donor actually stated.
_WEIGHT_SIMILARITY = 0.60
_WEIGHT_BUDGET = 0.15
_WEIGHT_LOCATION = 0.15
_WEIGHT_CAUSE = 0.10


@dataclass(frozen=True)
class Program:
    program_id: int
    name: str
    category: str
    description: str = ""
    location: str | None = None
    budget_needed: int | None = None
    organization_name: str = ""


@dataclass(frozen=True)
class MatchResult:
    program_id: int
    match_score: float
    matches_causes: bool
    matches_budget: bool
    matches_location: bool
    reason: str


def _money(value: float) -> str:
    if float(value).is_integer():
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _query_text(causes: Iterable[str], budget: float, location: str | None) -> str:
    parts = [CAUSE_SYNONYMS.get(cause, cause) for cause in causes if cause]
    if budget and budget > 0:
        parts.append(f"funding budget {_money(budget)} donate support")
    if location:
        parts.append(location)
    return " ".join(parts) or "charitable giving support"


def _program_text(program: Program) -> str:
    parts = [program.name, program.category]
    if program.description:
        parts.append(program.description)
    if program.location:
        parts.append(program.location)
    return " ".join(parts)


def _fits_budget(budget: float, budget_needed: int | None) -> bool:
    if not budget or budget <= 0 or budget_needed is None or budget_needed <= 0:
        return True
    return budget >= budget_needed


def _budget_factor(budget: float, budget_needed: int | None) -> float:
    """Unset budget or target -> neutral (0.5); within budget -> 1.0; a fairly
    large shortfall -> 0.7 (a partial pledge is realistic for PRD upfront
    pledges); a small offer from a large target -> 0.3."""
    if not budget or budget <= 0 or budget_needed is None or budget_needed <= 0:
        return 0.5
    if budget >= budget_needed:
        return 1.0
    if budget >= 0.5 * budget_needed:
        return 0.7
    return 0.3


def _locations_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    a_low, b_low = a.strip().lower(), b.strip().lower()
    return a_low in b_low or b_low in a_low


def _location_factor(location: str | None, program_location: str | None) -> float:
    if not location or not program_location:
        return 0.5
    return 1.0 if _locations_match(location, program_location) else 0.0


def _cause_factor(category: str, causes: list[str]) -> float:
    if not causes:
        return 0.7
    return 1.0 if category in causes else 0.55


def _reason(
    program: Program,
    *,
    matches_causes: bool,
    matches_budget: bool,
    matches_location: bool,
    causes: list[str],
    budget: float,
    location: str | None,
) -> str:
    label = CAUSE_LABELS.get(program.category, program.category)
    bits: list[str] = []
    if matches_causes:
        bits.append(f"it supports {label}")
    else:
        bits.append(f"it covers {label} rather than your chosen causes")
    if budget and budget > 0 and program.budget_needed is not None and program.budget_needed > 0:
        if matches_budget:
            bits.append(f"it fits your {_money(budget)} budget")
        else:
            ask = _money(program.budget_needed)
            pledge = _money(budget)
            bits.append(f"its {ask} ask is over your {pledge} budget for a full pledge")
    if location and program.location:
        if matches_location:
            bits.append(f"it is located in {program.location}")
        else:
            bits.append(f"it is based in {program.location}, outside your area")
    opener = f"Run by {program.organization_name}, " if program.organization_name else ""
    return f"{opener}this program matches because {', and '.join(bits)}."


def rank_matches(
    *,
    causes: list[str] | None,
    budget: float = 0,
    location: str | None = None,
    programs: list[Program],
    top_k: int | None = None,
) -> list[MatchResult]:
    """Rank ``programs`` against the donor's preferences, best first.

    Cause is a constraint: programs whose category is not among the donor's
    causes are skipped (unless the donor stated no causes, in which case the
    whole pool is fair game and similarity does the work). The result is
    deterministic: score descending, then program id ascending.
    """
    cleaned = [
        c.strip().lower() for c in causes or [] if c and c.strip()
    ]
    candidates = [p for p in programs if not cleaned or p.category in cleaned]
    if not candidates:
        return []

    query = _query_text(cleaned, budget, location)
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    matrix = vectorizer.fit_transform(
        [query] + [normalize(_program_text(p)) for p in candidates]
    )
    # Rows are L2-normalized, so dot products are cosine similarities.
    similarities = matrix[0].dot(matrix[1:].T).toarray()[0]

    results: list[MatchResult] = []
    for program, similarity in zip(candidates, similarities, strict=True):
        matches_causes = not cleaned or program.category in cleaned
        matches_budget = _fits_budget(budget, program.budget_needed)
        matches_location = _locations_match(location, program.location)
        score = (
            _WEIGHT_SIMILARITY * float(similarity)
            + _WEIGHT_BUDGET * _budget_factor(budget, program.budget_needed)
            + _WEIGHT_LOCATION * _location_factor(location, program.location)
            + _WEIGHT_CAUSE * _cause_factor(program.category, cleaned)
        )
        results.append(
            MatchResult(
                program_id=program.program_id,
                match_score=round(min(1.0, max(0.0, score)), 4),
                matches_causes=matches_causes,
                matches_budget=matches_budget,
                matches_location=matches_location,
                reason=_reason(
                    program,
                    matches_causes=matches_causes,
                    matches_budget=matches_budget,
                    matches_location=matches_location,
                    causes=cleaned,
                    budget=budget,
                    location=location,
                ),
            )
        )

    results.sort(key=lambda item: (-item.match_score, item.program_id))
    if top_k is not None:
        results = results[:top_k]
    return results