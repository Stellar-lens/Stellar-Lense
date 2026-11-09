"""Optional ML path for `detection.scoring`: train, save, load, predict.

A model *bundle* is a dict saved with joblib:

    {"model": <sklearn classifier>, "feature_names": [...],
     "model_id": str, "trained_on": str, "created_at": iso8601,
     "training_metrics": {...}}

Bundles are produced only by `scripts/train_model.py` (reproducible: fixed
seed, data generated in-process), never committed. Loading uses pickle via
joblib, so only load bundles you built yourself.

Requires the ``[ml]`` extra (scikit-learn, joblib, shap).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from detection.scoring import MODEL_FEATURE_NAMES


def train_bundle(
    X: list[list[float]],
    y: list[int],
    trained_on: str,
    seed: int = 7,
) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score

    model = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=seed)
    cv_f1 = cross_val_score(model, X, y, cv=5, scoring="f1")
    model.fit(X, y)
    fingerprint = hashlib.sha256(
        np.asarray(X, dtype=float).tobytes() + np.asarray(y).tobytes()
    ).hexdigest()[:12]
    return {
        "model": model,
        "feature_names": list(MODEL_FEATURE_NAMES),
        "model_id": f"rf-{fingerprint}",
        "trained_on": trained_on,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_metrics": {
            "n_samples": len(y),
            "n_positive": int(sum(y)),
            "cv_f1_mean": float(cv_f1.mean()),
            "cv_f1_std": float(cv_f1.std()),
        },
    }


def save_bundle(bundle: dict[str, Any], path: str | Path) -> Path:
    import joblib

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    return path


def load_bundle(path: str | Path) -> dict[str, Any] | None:
    """Load a bundle, or return None if the file doesn't exist.

    Raises ValueError if the bundle's feature list doesn't match the scorer's,
    which means it was trained against a different feature set.
    """
    path = Path(path)
    if not path.exists():
        return None
    import joblib

    bundle = joblib.load(path)
    if bundle.get("feature_names") != MODEL_FEATURE_NAMES:
        raise ValueError(
            f"model bundle {path} was trained on features {bundle.get('feature_names')}, "
            f"expected {MODEL_FEATURE_NAMES}; retrain with scripts/train_model.py"
        )
    return bundle


def predict_with_explanation(
    bundle: dict[str, Any], vector: list[float]
) -> tuple[float, dict[str, float] | None]:
    """Positive-class probability for one feature vector, plus SHAP values."""
    X = np.array([vector])
    probability = float(bundle["model"].predict_proba(X)[0][1])
    try:
        import shap
    except ImportError:
        return probability, None

    values = shap.TreeExplainer(bundle["model"]).shap_values(X)
    if isinstance(values, list):
        row = values[1][0]
    elif values.ndim == 3:
        row = values[0, :, 1]
    else:
        row = values[0]
    return probability, {name: float(v) for name, v in zip(bundle["feature_names"], row)}
