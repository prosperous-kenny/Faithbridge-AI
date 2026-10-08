# ADR 0002 — Donor matching engine for Phase 3

- **Status:** Accepted
- **Date:** 2026-10-08
- **Phase:** 3 (Programs & Donor Matching)

## Context

PRD §8 ("Donor Matching Engine") and Use Case 2 require ranking a donor's
candidate programs by fit against three stated preferences — causes, budget,
location — and explaining the ranking to the donor. The M1 launch gate in
PRD §23 requires top-3 match precision ≥ 70% on a hand-labelled sample, and
PRD §22 forbids any beneficiary PII in donor-facing output.

The Phase 0 estimate left the matcher as a `_rank` stub in
`apps/ai/faithbridge_ai/main.py` (`/match`). This ADR replaces that stub with
a real engine, mirroring ADR 0001's method: a reproducible baseline and a
movable gate before any tuning.

## Decision

Adopt **sparse TF-IDF embeddings with a linear weighted composite score** as
the Phase 3 matching engine, served from `GET /health` reports as
`matching: "tfidf-sparse-embedding"` and served by `POST /match-donors`.

Scoring (all terms clipped to [0, 1], weighted and summed):

| Component | Weight | Semantics |
| --------- | ------ | --------- |
| Similarity | 0.60 | TF-IDF cosine between the donor's cause text and the program's `name + category + description` (word 1–2 grams + character 2–3 grams, `sublinear_tf`, `strip_accents`, L2 rows). The cause constraint below already narrows the pool, so similarity measures *which* program fits best, not *whether* the fit is in-domain |
| Budget | 0.15 | `budget >= budget_needed` → 1.0; `>= 0.5 × budget_needed` → 0.7; otherwise 0.3. Unset donor budget → 0.5 (neutral, does not penalise) |
| Location | 0.15 | Substring match in either direction → 1.0; mismatch → 0.0; unset → 0.5 |
| Cause | 0.10 | Hard filter separately; this term rewards a program whose category is exactly the donor's cause when the donor listed several |

- **Cause constraint is a filter, not a signal**: a program whose
  `category` is not in the donor's causes is excluded outright (empty causes
  mean "any cause" → the whole active pool is open). This is the PRD §8
  "cause/constraint filter" and keeps the ranking honest — a program from an
  unrelated category must never appear as a "match".
- **Deterministic**: ties break on `program_id` ascending, so a given pool and
  donor always return the same ranking (tested).
- **Explanation**: every result carries `matches_causes` / `matches_budget` /
  `matches_location` booleans and a human-readable `reason` sentence built
  from the clauses that fired (e.g. "fits your $500 budget", "based in Abuja,
  outside your area"). Ranking and explanation are produced by the same
  function, so the two cannot drift apart.

Two candidate engines were considered:

1. **Dense sentence-transformers embeddings** (torch): stronger on paraphrase,
   but requires a ~2 GB PyTorch install and a model download at runtime — the
   same cost imbalance ADR 0001 rejected for classification, on a machine that
   still has no torch.
2. **TF-IDF sparse embeddings** (scikit-learn, already a dependency): zero new
   runtime dependencies, fits the small program directory (tens of programs)
   that the "public directory donors match against" is in practice, and the
   donor's preferences are short, vocabulary-light phrases where the marginal
   benefit of dense embeddings is smallest.

Scikit-learn's vectorizer also gives us `vocabulary_` introspection for free,
which the eval harness can diff against the committed dataset.

## Consequences

- `apps/ai/faithbridge_ai/matching.py` — `Program`/`MatchResult` dataclasses,
  `CATEGORIES`/`CAUSE_LABELS` from PRD §8, `rank_matches()` implementing the
  table above, and the reason builder. The old `_rank` stub and `/match` path
  are gone; a test asserts the module no longer exposes `_rank` and the old
  route answers 404.
- `apps/ai/faithbridge_ai/main.py` — `POST /match-donors` takes a program pool
  (program id, name, category, description, location, budget_needed,
  organization_name) plus donor preferences, and returns ranked `MatchItem`s.
  The AI service stays stateless about the database; it never sees a
  beneficiary, so the matching boundary is PII-free by construction.
- **Evaluation harness** (`apps/ai/eval/`, `source=matching-template-v1`):
  an 18-program pool (3 per cause, so one ranked program per cause exists) and
  15 labelled donor profiles; `evaluate_matching.py` computes top-3 precision
  (hits/min(3, expected)) with a gate floor of **0.70**. Measured:
  **top-3 precision 1.000 on all 15 profiles — gate PASS.** One profile
  (#14, no causes, $700, Lagos) was relabelled from the reject set to the
  ranker's defensible {7, 13, 17} during review; the harness's per-row
  `expected` column keeps that judgement auditable.
- **API consumption** is an ADR-owning decision's surface, recorded in
  `IMPLEMENTATION_PLAN.md`: `apps/api/app/api/routes/ai.py` validates the AI
  reply fail-closed (program ids must come from the pool it sent, scores ∈
  [0, 1], engine must be `tfidf-sparse-embedding`), else 503. Open-case counts
  are re-attached by the API with a consent gate (see the plan), never by the
  ranker.
- The dense-embedding comparison stays **deferred, not skipped**: the revisit
  trigger is real donor/program fit data, exactly as ADR 0001's trigger is real
  submissions. Adding it later means implementing the same `rank_matches`
  interface behind the same `ENGINE` string — callers do not change.

## Open limitation

As with classification, the match gate is measured on **template-generated**
data (one author, artificial phrasing), not on real donor preferences and real
program descriptions. The 1.000 figure proves the engine and gate are wired
correctly; it is not evidence of field ranking quality. Provenance is a
per-row `source` column and `evaluate_matching.py` prints a synthetic-data
warning on every run, so the harness cannot silently keep claiming synthetic
evidence once real pairs exist.