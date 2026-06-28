"""Tests for evaluation.backtest.run_backtest (Issue #283)."""

import json

import numpy as np
import pandas as pd

from evaluation.backtest import run_backtest

PAIRS = ["XLM:USDC", "XLM:AQUA"]


def _synthetic_dataset(tmp_path, n=100, labels=None, name="dataset.parquet"):
    rng = np.random.default_rng(42)
    if labels is None:
        labels = rng.choice(["wash", "clean"], size=n)
    df = pd.DataFrame(
        {
            "label": labels,
            "asset_pair": rng.choice(PAIRS, size=n),
            "feature_a": rng.normal(size=n),
        }
    )
    path = tmp_path / name
    df.to_parquet(path)
    return str(path)


def _score_from_feature_a(row) -> float:
    return float(1 / (1 + np.exp(-row["feature_a"])))


def test_backtest_on_synthetic_dataset_produces_valid_report(tmp_path):
    dataset_path = _synthetic_dataset(tmp_path)
    output_dir = tmp_path / "out"

    report = run_backtest(
        dataset_path,
        {"predict_fn": _score_from_feature_a, "name": "synthetic-test"},
        str(output_dir),
    )

    assert (output_dir / "backtest_report.json").exists()
    assert (output_dir / "pr_curve.png").exists()
    with open(output_dir / "backtest_report.json") as f:
        on_disk = json.load(f)
    assert on_disk == report
    assert report["row_count"] == 100
    assert "model_config_hash" in report
    assert {"precision", "recall", "f1", "average_precision", "roc_auc"}.issubset(report)
    assert set(report["per_asset_pair"]) == set(PAIRS)


def test_all_positive_and_all_negative_labels_produce_finite_metrics(tmp_path):
    for i, labels in enumerate((["wash"] * 50, ["clean"] * 50)):
        dataset_path = _synthetic_dataset(tmp_path, n=50, labels=labels, name=f"ds_{i}.parquet")
        output_dir = tmp_path / f"out_{i}"

        report = run_backtest(dataset_path, {"predict_fn": _score_from_feature_a}, str(output_dir))

        for key in ("precision", "recall", "f1", "average_precision", "roc_auc"):
            assert np.isfinite(report[key]), (key, report[key])


def test_threshold_flag_filters_predictions_before_metrics(tmp_path):
    dataset_path = _synthetic_dataset(tmp_path, n=50)

    low_report = run_backtest(
        dataset_path, {"predict_fn": _score_from_feature_a}, str(tmp_path / "low"), threshold=0.01
    )
    high_report = run_backtest(
        dataset_path, {"predict_fn": _score_from_feature_a}, str(tmp_path / "high"), threshold=0.99
    )

    assert low_report["confusion_matrix"] != high_report["confusion_matrix"]
    assert low_report["threshold"] == 0.01
    assert high_report["threshold"] == 0.99


def test_report_never_contains_wallet_addresses(tmp_path):
    dataset_path = _synthetic_dataset(tmp_path, n=20)

    report = run_backtest(dataset_path, {"predict_fn": _score_from_feature_a}, str(tmp_path / "out"))

    assert "wallet" not in json.dumps(report).lower()
