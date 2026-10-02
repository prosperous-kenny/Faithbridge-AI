# ADR 0001 — Classifier model selection for Phase 0

- **Status:** Accepted
- **Date:** 2026-10-02
- **Phase:** 0 (Spike & Foundation)

## Context

The Phase 0 goal (docs/IMPLEMENTATION_PLAN.md, task 4) is to replace the
rule-based keyword classifier with a real baseline and pick a winner against a
measurable evaluation, before any tuning. The M1 launch gate in PRD §23 requires
classification accuracy ≥ 85%.

Two candidates were considered:

1. **TF-IDF + linear model** (`scikit-learn`) — word and character n-gram
   features into a linear SVM.
2. **Embedding model** (`sentence-transformers`) — pretrained semantic
   vectors with a classifier head.

## Decision

Adopt **TF-IDF + LinearSVC** as the Phase 0 baseline and ship it.

Measured on a held-out stratified 30% split (seed 42, 142 train / 62 test):

| Model | Overall accuracy | Notes |
| ----- | ---------------- | ----- |
| TF-IDF + LinearSVC | **90.3%** | Passes the ≥85% gate; no category below 0.70 |
| Rule-based keywords (current) | 80.6% | Fails: medical recall 0.40, emergency precision 0.56 |

Full per-category numbers are in `apps/ai/eval/results.txt`, regenerable with
`python eval/evaluate.py`.

Character 3-5 grams are included alongside word 1-2 grams because submitted
needs are frequently misspelled or abbreviated; word features alone miss those
variants.

Sentence-transformers was not adopted yet, for two reasons. First, it requires
a PyTorch model download at runtime, which makes the default classification
path heavy for a Phase 0 spike and complicates CI. Second, on the current
dataset it is unlikely to beat TF-IDF by enough to matter — the residual errors
are semantic ambiguities, not vocabulary gaps.

The embedding comparison remains open and should be revisited once real
submissions exist to evaluate against.

## Consequences

- The API contract is unchanged: `faithbridge_ai.classifier.classify()` keeps
  its shape, so the FastAPI service and the web app are unaffected.
- `faithbridge_ai.baseline.TfidfClassifier` is the new model, with
  `decision_scores()` exposed for the confidence-gated human triage the risk
  table in the plan calls for.
- Adding an embedding model later means implementing the same predict
  interface, not changing callers.
- Urgency scoring is deliberately *not* part of this decision. Category
  accuracy and urgency calibration are separate; urgency thresholds get fitted
  against labeled urgency in Phase 2, per the plan.

## Open limitation

The evaluation dataset (`apps/ai/eval/dataset.csv`, 204 rows across six
categories) is **template-generated**, not real beneficiary submissions. The
90.3% figure measures performance on natural-phrasing templates written for
this harness, which is a weaker proxy than real data and likely optimistic.
The dataset exists so the harness and gate are reproducible; it is not
evidence of field accuracy. Real submissions must replace it before the M1
launch gate in PRD §23 can be claimed.
