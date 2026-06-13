import json
import os

import pytest

from detection.model_training import (
    MODEL_REGISTRY,
    save_metrics_report,
    save_models,
    split_features_labels,
    train_models,
)
from scripts.generate_synthetic_dataset import generate_synthetic_dataset


@pytest.fixture(scope="module")
def trained_results():
    df = generate_synthetic_dataset(n_wallets=60, seed=1)
    return train_models(df, test_size=0.3, random_state=1), df


def test_split_features_labels_excludes_wallet_and_label():
    df = generate_synthetic_dataset(n_wallets=10, seed=1)
    X, y = split_features_labels(df)
    assert "wallet" not in X.columns
    assert "label" not in X.columns
    assert len(X) == len(y)


def test_train_models_returns_metrics_for_each_model(trained_results):
    results, _ = trained_results
    assert set(results) == set(MODEL_REGISTRY)
    for result in results.values():
        assert set(result["metrics"]) == {"auc_roc", "pr_auc", "f1"}
        assert 0.0 <= result["metrics"]["auc_roc"] <= 1.0


def test_save_models_and_metrics_report(tmp_path, trained_results):
    results, _ = trained_results
    model_dir = str(tmp_path)

    save_models(results, model_dir)
    for name in MODEL_REGISTRY:
        assert os.path.exists(os.path.join(model_dir, f"{name}.joblib"))

    metrics_path = save_metrics_report(results, model_dir)
    assert os.path.exists(metrics_path)

    with open(metrics_path) as f:
        metrics = json.load(f)
    assert set(metrics) == set(MODEL_REGISTRY)
