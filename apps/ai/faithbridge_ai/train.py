"""Build and persist the baseline classifier artifact.

Run:  python -m faithbridge_ai.train

The artifact is a build output, not source: it is gitignored and rebuilt from
the labeled dataset. The AI service also trains in-process at startup when no
artifact exists, so this command exists for reproducible, inspectable builds
rather than as a required deploy step.
"""

import logging
import sys

from faithbridge_ai import baseline


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    model = baseline.train_from_dataset()
    path = baseline.save(model)

    reloaded = baseline.load(path)
    if not reloaded.is_fitted:
        print("FAIL: saved artifact did not round-trip")
        return 1

    baseline.install_model(reloaded)
    sample = "Family of four facing eviction in two weeks and needs rent help"
    result = baseline.classify(sample)

    print(f"saved {baseline.MODEL_ENGINE} to {path}")
    print(f"training data: {baseline.dataset_path()}")
    print(f"sample: {sample!r} -> {result['category']} ({result['confidence']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
