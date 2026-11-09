import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from detection.model import load_bundle, save_bundle, train_bundle  # noqa: E402
from detection.scoring import MODEL_FEATURE_NAMES  # noqa: E402

X = [[0.9, 0.8, 0.4, 0.9, 0.3, 0.04]] * 12 + [[0.2, 0.0, 0.0, 0.1, 0.1, 0.006]] * 12
Y = [1] * 12 + [0] * 12


def test_bundle_round_trip(tmp_path):
    bundle = train_bundle(X, Y, trained_on="fixture")
    path = save_bundle(bundle, tmp_path / "m.joblib")
    loaded = load_bundle(path)
    assert loaded["model_id"] == bundle["model_id"]
    assert loaded["feature_names"] == MODEL_FEATURE_NAMES
    assert loaded["training_metrics"]["n_samples"] == 24


def test_model_id_is_deterministic():
    assert train_bundle(X, Y, "a")["model_id"] == train_bundle(X, Y, "b")["model_id"]


def test_missing_bundle_returns_none(tmp_path):
    assert load_bundle(tmp_path / "absent.joblib") is None


def test_feature_mismatch_is_rejected(tmp_path):
    bundle = train_bundle(X, Y, trained_on="fixture")
    bundle["feature_names"] = ["something_else"]
    path = save_bundle(bundle, tmp_path / "m.joblib")
    with pytest.raises(ValueError, match="retrain"):
        load_bundle(path)


@pytest.mark.slow
def test_training_script_runs(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "train_model.py"
    spec = importlib.util.spec_from_file_location("train_model", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--out", str(tmp_path / "m.joblib")]) == 0
    assert load_bundle(tmp_path / "m.joblib")["trained_on"].startswith("synthetic")
