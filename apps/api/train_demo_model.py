"""Train the toy ensemble artifact backing this demo API's ML scoring path.

Without models/ensemble.joblib, detection.model_inference falls back to the
Phase 1 weighted heuristic and never computes SHAP attributions. This script
fits a small RandomForestClassifier on synthetic feature vectors shaped
like the wash-trading and organic-activity patterns already seeded in
api/storage.py, so the demo API's ML path — and therefore SHAP
explainability — is actually reachable instead of silently unavailable.

Not a real trained model: it's illustrative, matching this demo's synthetic
data. Re-run after changing detection/model_inference.py's FEATURE_WEIGHTS
keys or their order, since the feature vector order must match exactly.

Usage: uv run --project apps/api python scripts/train_demo_model.py
"""

import os
import random

import joblib
from sklearn.ensemble import RandomForestClassifier

from detection.model_inference import FEATURE_WEIGHTS

random.seed(7)

FEATURE_NAMES = list(FEATURE_WEIGHTS.keys()) + ["benford_mad"]


def _sample(wash: bool) -> list[float]:
    """One synthetic feature vector, jittered around a wash-like or
    clean-like profile so the model sees some spread, not five exact
    points repeated."""
    if wash:
        return [
            random.uniform(0.75, 1.0),  # counterparty_concentration_ratio
            random.uniform(0.5, 1.0),  # round_trip_trade_frequency
            random.uniform(0.0, 0.6),  # self_matching_rate
            random.uniform(0.6, 1.0),  # intra_minute_clustering_coefficient
            random.uniform(0.0, 0.4),  # off_hours_activity_ratio
            random.uniform(0.02, 0.06),  # benford_mad
        ]
    return [
        random.uniform(0.05, 0.4),
        random.uniform(0.0, 0.1),
        0.0,
        random.uniform(0.0, 0.3),
        random.uniform(0.0, 0.3),
        random.uniform(0.002, 0.014),
    ]


def main() -> None:
    X = [_sample(wash=True) for _ in range(60)] + [
        _sample(wash=False) for _ in range(60)
    ]
    y = [1] * 60 + [0] * 60

    model = RandomForestClassifier(
        n_estimators=100, max_depth=4, random_state=7
    )
    model.fit(X, y)

    out_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "ensemble.joblib")
    joblib.dump(model, out_path)
    print(f"wrote {out_path}")
    print(f"feature order: {FEATURE_NAMES}")
    print(f"train accuracy: {model.score(X, y):.3f}")


if __name__ == "__main__":
    main()
