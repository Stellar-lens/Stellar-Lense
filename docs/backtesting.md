# Backtesting

## Historical backtest framework

`evaluation/backtest.py` replays a labelled, held-out dataset through the
detection pipeline in batch mode and produces a standardized performance
report, so comparing model versions or catching a regression before
deployment doesn't require manually running scripts and comparing numbers
by hand.

### Dataset format

A Parquet file with:

* `label` -- either hard labels (`"wash"` / `"clean"`, case-insensitive, or
  `0`/`1`/bool) or soft labels (a `0.0`-`1.0` confidence float, thresholded
  at `0.5` to binarize).
* `asset_pair` -- used for the per-asset-pair metric breakdown. Defaults to
  `"unknown"` if the column is absent.
* whatever feature columns the scoring function needs (the live
  `RiskScorer` ensemble by default, or an injected `predict_fn` for offline
  replay against fixed predictions).

### Running a backtest

```bash
python -m evaluation.backtest path/to/dataset.parquet path/to/output_dir --threshold 0.6
```

Or from Python, to evaluate a specific model config / injected scoring
function:

```python
from evaluation.backtest import run_backtest

report = run_backtest(
    dataset_path="held_out.parquet",
    model_config={"name": "ensemble-v3"},
    output_dir="reports/ensemble-v3",
    threshold=0.6,
)
```

Writes `output_dir/backtest_report.json` and `output_dir/pr_curve.png`.

### Interpreting the report

* `model_config_hash` -- SHA-256 (truncated) of `model_config`, so the
  report is traceable to an exact configuration. Excludes any injected
  `predict_fn` callable.
* `threshold` -- the risk-probability cutoff used to binarize predictions
  for `precision`/`recall`/`f1`/`confusion_matrix`.
* `precision` / `recall` / `f1` -- at `threshold`, with `zero_division=0`
  so a label split with no positives (or no predicted positives) reports
  `0.0` instead of raising.
* `average_precision` / `roc_auc` -- threshold-independent ranking metrics;
  both default to a finite placeholder (`0.0` / `0.5` respectively) when
  the dataset has only one label class, since neither metric is defined
  in that case.
* `confusion_matrix` -- always a full 2x2 `[[tn, fp], [fn, tp]]`, even when
  one class is entirely absent from the dataset.
* `per_asset_pair` -- the same precision/recall/f1 breakdown, keyed by
  asset pair.

The report never includes wallet addresses or any other per-row
identifier -- only aggregate metrics and the asset-pair key, which is not
considered sensitive.
