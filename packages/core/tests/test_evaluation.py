import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "evaluation"
sys.path.insert(0, str(EVAL_DIR))
_spec = importlib.util.spec_from_file_location("evaluate", EVAL_DIR / "evaluate.py")
evaluate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate)


def test_wilson_interval_bounds():
    assert evaluate.wilson(0, 0) is None
    lo, hi = evaluate.wilson(5, 10)
    assert 0.2 < lo < 0.5 < hi < 0.8
    lo, hi = evaluate.wilson(0, 1)
    assert lo == 0.0 and hi > 0.7  # one observation tells you little


def test_auc_perfect_random_and_ties():
    assert evaluate.auc([90, 80, 10, 5], [1, 1, 0, 0]) == 1.0
    assert evaluate.auc([10, 5, 90, 80], [1, 1, 0, 0]) == 0.0
    assert evaluate.auc([50, 50], [1, 0]) == 0.5
    assert evaluate.auc([50], [1]) is None


def test_metrics_confusion_counts():
    df = pd.DataFrame({"score": [80, 60, 40, 10], "label": [1, 0, 1, 0]})
    m = evaluate.metrics(df, 50)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == pytest.approx(0.5)
    assert m["recall"] == pytest.approx(0.5)


def test_committed_dataset_scores_and_has_labels():
    from api_free_scoring import score_labelled

    labelled = pd.read_csv(EVAL_DIR / "data" / "labelled_wallets.csv", dtype={"label": str})
    trades = pd.read_csv(EVAL_DIR / "data" / "trades.csv.gz")
    scored = score_labelled(labelled.head(20), trades)
    assert scored["score"].between(0, 100).all()
    assert set(labelled["label"]) <= {"0", "1", "unknown"}
