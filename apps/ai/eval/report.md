# Phase 0 classification evaluation

Regenerate everything in this file with:

```bash
python eval/build_dataset.py   # writes eval/dataset.csv (204 rows)
python eval/evaluate.py        # writes eval/results.txt and prints below
```

## Setup

- Dataset: 204 labeled statements, 34 per category, six PRD §11 categories
  (`food`, `housing`, `medical`, `education`, `employment`, `emergency`)
- Provenance: all 204 rows carry `source=template-v1`; there are no real
  beneficiary submissions in it yet. `evaluate.py` prints this provenance block
  and a synthetic-data warning on every run.
- Split: stratified, 30% held out, `random_state=42` — 142 train / 62 test
- Deterministic: re-running produces identical numbers
- Leakage: every template contributes exactly one row, so there are no duplicate
  statements spanning the train/test boundary. This was verified, not assumed —
  `tests/test_dataset_integrity.py` asserts uniqueness, per-category balance,
  and that the committed CSV matches the generator exactly.

## Results

| Model | Overall accuracy | Gate (≥85%, no category <70%) |
| ----- | ---------------- | ------------------------------ |
| TF-IDF + LinearSVC | **90.3%** | PASS |
| Rule-based keywords (current) | 80.6% | FAIL |

### TF-IDF + LinearSVC, per category

| Category | Support | Precision | Recall | F1 |
| -------- | ------- | --------- | ------ | -- |
| food | 11 | 1.000 | 0.909 | 0.952 |
| housing | 11 | 1.000 | 0.909 | 0.952 |
| medical | 10 | 0.818 | 0.900 | 0.857 |
| education | 10 | 0.875 | 0.700 | 0.778 |
| employment | 10 | 0.833 | 1.000 | 0.909 |
| emergency | 10 | 0.909 | 1.000 | 0.952 |

### Rule-based, per category

| Category | Support | Precision | Recall | F1 |
| -------- | ------- | --------- | ------ | -- |
| food | 11 | 1.000 | 1.000 | 1.000 |
| housing | 11 | 1.000 | 0.727 | 0.842 |
| medical | 10 | 1.000 | 0.400 | 0.571 |
| education | 10 | 0.875 | 0.700 | 0.778 |
| employment | 10 | 0.769 | 1.000 | 0.870 |
| emergency | 10 | 0.556 | 1.000 | 0.714 |

## Error analysis (TF-IDF)

Six errors on the held-out split, all semantic ambiguities rather than
vocabulary gaps:

- `education → employment` — "A young person needs help completing secondary
  education" (education framed as a benefit for getting work)
- `medical → education` — "cost of seeing a specialist privately" (no explicit
  medical noun; "specialist" reads as academic)
- `education → medical` — "My child needs extra tutoring" ("child" pulls toward
  the medical class)
- `food → employment` — "I lost my job and cannot feed my family, we need food
  support" (the unemployment clause dominates)
- `housing → emergency` — "help staying in our home while we look for work"
  (no eviction language, so it reads as generic urgent need)
- `education → medical` — "A student needs help with coursework costs"

`education` is the weakest category (recall 0.700, at the floor) and the only
one that fails to clear it with margin. The confusion is genuinely two-sided:
education↔medical and education↔employment. This is the category to watch
once real data arrives.

The rule-based classifier's two failures are more structural:

- **medical recall 0.400** — the keyword list lacks `surgery`, `operation`,
  `prescription`, `insulin`, `dialysis`, `cancer`, and similar terms, so most
  medical statements score zero and fall through to the emergency fallback.
- **emergency precision 0.556** — `emergency` is the fallback whenever nothing
  else scores, so it absorbs unrelated requests. 5 of 11 housing statements
  landed there.

## Chosen model

**TF-IDF + LinearSVC**, word 1-2 grams plus char 3-5 grams into a linear SVM.
Rationale and the sentence-transformers comparison are in
`docs/adr/0001-model-selection.md`.

## Limitation on these numbers

The dataset is **template-generated**, not real beneficiary submissions. These
figures measure performance on natural-phrasing templates written for this
harness. They are reproducible and they make the gate checkable, but they are a
weaker proxy than real data and are likely optimistic. Two specific reasons the
number is optimistic:

1. The 204 templates were written by the same author as the model was tuned
   against, so phrasing regularities in the templates are learnable.
2. Templates within a category share vocabulary and phrasing, so a model that
   has seen 28 housing templates is tested on 6 written in the same style.

The dataset's purpose is to make accuracy measurable *before* tuning, which it
does. Real submissions must replace it before the M1 launch gate in PRD §23 can
be claimed as met.

To keep that caveat from being lost, provenance is stored per row rather than
only in prose: `dataset.csv` has a `source` column, the harness reports the
provenance mix and warns while the data is entirely synthetic, and the warning
clears itself once rows from another source are added.
