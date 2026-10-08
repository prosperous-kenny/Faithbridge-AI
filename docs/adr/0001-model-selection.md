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

- The AI service now serves the model. `faithbridge_ai.baseline.classify()`
  routes to the fitted `TfidfClassifier` when one is installed and to the
  rule-based matcher only as an explicit fallback, reporting which engine
  answered via the `classifier` field on `/classify` and on `/health`. This was
  corrected in Phase 0 task 4: the original "swap" only added the model and
  left `classify()` delegating to the rules, so the decision above was recorded
  without the model ever serving a request.
- The model is trained once per process at startup (or loaded from
  `apps/ai/models/baseline.joblib`, a gitignored build output) and served from
  memory. `python -m faithbridge_ai.train` builds the artifact explicitly.
- `POST /classify` gained two additive fields, `classifier` and `confidence`.
  `confidence` is a softmax over SVM margins and is **not** a calibrated
  probability; it exists to route low-confidence cases to human triage and must
  not be shown to beneficiaries as a percentage.
- `faithbridge_ai.baseline.TfidfClassifier` exposes `decision_scores()` for the
  confidence-gated human triage the risk table in the plan calls for.
- Urgency scoring is deliberately *not* part of this decision, and the swap does
  not change it: category comes from the model, while `urgency_score` and
  `priority` come from `classifier.score_urgency()`. Urgency thresholds get
  fitted against labeled urgency in Phase 2, per the plan. A test asserts the two
  paths produce identical urgency so this separation cannot rot silently.
- Adding an embedding model later means implementing the same predict interface
  and installing it, not changing callers.

## Open limitation

The evaluation dataset (`apps/ai/eval/dataset.csv`, 204 rows across six
categories) is **template-generated**, not real beneficiary submissions. The
90.3% figure measures performance on natural-phrasing templates written for
this harness, which is a weaker proxy than real data and likely optimistic.
The dataset exists so the harness and gate are reproducible; it is not
evidence of field accuracy. Real submissions must replace it before the M1
launch gate in PRD §23 can be claimed.

Because a prose caveat is easy to lose, provenance is now recorded per row in a
`source` column, and `python eval/evaluate.py` prints a provenance block plus a
warning to `eval/results.txt` on every run while the dataset is entirely
synthetic. The warning disappears automatically when rows from another source
are present, so the harness cannot quietly keep claiming synthetic evidence.

