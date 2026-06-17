"""Train the LedgerLens ensemble classifiers (RF, XGBoost, LightGBM).

Run as a script against a labelled feature matrix (see
`scripts/generate_synthetic_dataset.py` for a synthetic one, or the
"Open dataset release" roadmap item for the real thing):

    python -m detection.model_training --data-path data/synthetic_dataset.parquet

This trains each model in `MODEL_REGISTRY` with SMOTE-balanced training
data, evaluates AUC-ROC / PR-AUC / F1 on a held-out split, writes the
artifacts to `config.MODEL_DIR`, and writes `metrics.json` alongside them.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime

import joblib
import pandas as pd
from imblearn.over_sampling import SMOTE
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import auc, f1_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

MODEL_REGISTRY = {
    "random_forest": RandomForestClassifier,
    "xgboost": XGBClassifier,
    "lightgbm": LGBMClassifier,
}

FEATURE_COLUMNS_EXCLUDE = {"wallet", "label"}


def compute_feature_schema_hash(feature_columns: list[str]) -> str:
    """Compute a SHA-256 hash of the sorted feature column names."""
    sorted_cols = sorted(feature_columns)
    schema_str = "\n".join(sorted_cols)
    return f"sha256:{hashlib.sha256(schema_str.encode()).hexdigest()}"


def load_training_data(path: str) -> pd.DataFrame:
    """Load a labelled feature matrix (output of `build_feature_matrix` plus
    a `label` column: 1 = wash trading, 0 = legitimate)."""
    return pd.read_parquet(path)


def split_features_labels(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    feature_cols = [c for c in df.columns if c not in FEATURE_COLUMNS_EXCLUDE]
    return df[feature_cols], df["label"]


def train_models(df: pd.DataFrame, test_size: float = 0.2, random_state: int = 42) -> dict:
    """Train all models in `MODEL_REGISTRY` and return fitted estimators
    plus evaluation metrics and split info.

    Returns:
        {
          "results": {
            "random_forest": {"model": ..., "metrics": {...}},
            ...
          },
          "feature_columns": [...],
          "n_train": int,
          "n_test": int
        }
    """
    X, y = split_features_labels(df)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    smote = SMOTE(random_state=random_state)
    X_train_res, y_train_res = smote.fit_resample(X_train, y_train)

    results = {}
    for name, model_cls in MODEL_REGISTRY.items():
        model = model_cls(random_state=random_state)
        model.fit(X_train_res, y_train_res)

        probs = model.predict_proba(X_test)[:, 1]
        preds = model.predict(X_test)

        precision, recall, _ = precision_recall_curve(y_test, probs)

        results[name] = {
            "model": model,
            "metrics": {
                "auc_roc": float(roc_auc_score(y_test, probs)),
                "pr_auc": float(auc(recall, precision)),
                "f1": float(f1_score(y_test, preds)),
            },
        }

    return {
        "results": results,
        "feature_columns": list(X.columns),
        "n_train": len(X_train),
        "n_test": len(X_test),
    }


def save_models(results: dict, model_dir: str | None = None) -> None:
    model_dir = model_dir or config.MODEL_DIR
    os.makedirs(model_dir, exist_ok=True)
    for name, result in results.items():
        joblib.dump(result["model"], os.path.join(model_dir, f"{name}.joblib"))


def save_training_artifacts(
    training_output: dict,
    data_path: str,
    model_dir: str | None = None,
) -> None:
    """Write metrics.json and model_metadata.json to the model directory.

    NOTE: data_path is stored as-is from the CLI. If this path contains
    sensitive information (e.g. S3 credentials), it will be persisted
    in the metadata file.
    """
    model_dir = model_dir or config.MODEL_DIR
    os.makedirs(model_dir, exist_ok=True)

    results = training_output["results"]
    feature_columns = training_output["feature_columns"]

    # metrics.json
    metrics_path = os.path.join(model_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump({name: result["metrics"] for name, result in results.items()}, f, indent=2)

    # model_metadata.json
    metadata = {
        "trained_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "data_path": data_path,
        "n_training_rows": training_output["n_train"],
        "n_test_rows": training_output["n_test"],
        "feature_columns": feature_columns,
        "feature_schema_hash": compute_feature_schema_hash(feature_columns),
        "model_names": list(results.keys()),
        "python_version": sys.version.split()[0],
        "ledgerlens_version": "0.2.0",
    }

    metadata_path = os.path.join(model_dir, "model_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Saved metrics to %s", metrics_path)
    logger.info("Saved model metadata to %s", metadata_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the LedgerLens ensemble classifiers")
    parser.add_argument(
        "--data-path",
        required=True,
        help="Path to a labelled feature matrix (parquet) with a 'label' column",
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Directory to write trained model artifacts and metrics.json (default: MODEL_DIR)",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logger.info("Loading training data from %s", args.data_path)
    df = load_training_data(args.data_path)
    logger.info("Loaded %d rows", len(df))

    training_output = train_models(df, test_size=args.test_size, random_state=args.random_state)
    results = training_output["results"]
    for name, result in results.items():
        logger.info("%s metrics: %s", name, result["metrics"])

    save_models(results, args.model_dir)
    save_training_artifacts(training_output, args.data_path, args.model_dir)
    logger.info("Saved models and artifacts to %s", args.model_dir or config.MODEL_DIR)


if __name__ == "__main__":
    main()
