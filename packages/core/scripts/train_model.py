"""Train the optional ML model bundle used by `detection.scoring`.

Reproducible by construction: the training data is generated in-process by
`ingestion.synthetic_data.generate_synthetic_dataset` from fixed seeds, so
the same command always yields the same model and model_id.

This model is trained on SYNTHETIC data only. Its bundle says so in
``trained_on``, and the API echoes that string next to every score it
produces. Treat its scores as a demonstration of the ML path, not as a
model validated on real Stellar wash trading.

Usage (from the repo root):

    uv run --package stellar-lense-core --extra ml \
        python packages/core/scripts/train_model.py --out models/model.joblib
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detection.model import save_bundle, train_bundle  # noqa: E402
from detection.scoring import (  # noqa: E402
    benford_report,
    model_feature_vector,
    wallet_features,
)
from ingestion.synthetic_data import generate_synthetic_dataset  # noqa: E402

SEEDS = (11, 23, 37, 41, 53)
AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
TRAINED_ON = (
    "synthetic: ingestion.synthetic_data.generate_synthetic_dataset, "
    f"seeds {list(SEEDS)}; not validated on real Stellar data"
)


def build_training_set() -> tuple[list[list[float]], list[int]]:
    X: list[list[float]] = []
    y: list[int] = []
    for seed in SEEDS:
        trades, _meta, _events, labels = generate_synthetic_dataset(
            n_normal_accounts=40, n_wash_rings=6, as_of=AS_OF, seed=seed
        )
        for wallet, label in sorted(labels.items()):
            own = trades[(trades["base_account"] == wallet) | (trades["counter_account"] == wallet)]
            features = wallet_features(trades, wallet)
            benford = benford_report(own["base_amount"].astype(float).tolist())
            X.append(model_feature_vector(features, benford))
            y.append(label)
    return X, y


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="models/model.joblib", help="bundle output path")
    args = parser.parse_args(argv)

    X, y = build_training_set()
    bundle = train_bundle(X, y, trained_on=TRAINED_ON)
    path = save_bundle(bundle, args.out)
    m = bundle["training_metrics"]
    print(f"wrote {path} model_id={bundle['model_id']}")
    print(
        f"samples={m['n_samples']} positives={m['n_positive']} "
        f"5-fold CV F1 on synthetic data={m['cv_f1_mean']:.3f}±{m['cv_f1_std']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
