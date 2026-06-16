# Add Model Versioning and Stale Model Detection

**Label:** `intermediate` | `enhancement` | `detection` | `mlops`
**Difficulty:** Intermediate
**Area:** `detection/model_training.py`, `detection/model_inference.py`

> **Blocks:** Issue #010 (Continuous Retraining with Drift Detection) requires the `model_metadata.json` sidecar and `feature_schema_hash` introduced here. Merge this issue before starting #010.

---

## Summary

Model artifacts (`.joblib` files) are written to `config.MODEL_DIR` with no associated metadata: no training timestamp, no feature schema fingerprint, no dataset statistics. `RiskScorer` blindly loads whatever `.joblib` files it finds and scores wallets without verifying that the models match the current feature schema.

This creates a class of silent production bugs:
- A model trained on an older feature schema (e.g. before a new Benford window was added) is loaded and silently scores on a mismatched feature row — producing garbage scores with no error.
- There is no way to know how old a production model is or what data it was trained on.
- Retraining always overwrites artifacts in-place; there is no rollback path.

This issue asks you to implement a lightweight model versioning system using a `model_metadata.json` sidecar file and a feature-schema fingerprint check at load time.

---

## Detailed Description

### What to implement

**`detection/model_training.py`**:
- After saving models, write a `model_metadata.json` file to `MODEL_DIR` alongside `metrics.json`:

```json
{
  "trained_at": "2026-06-16T12:00:00Z",
  "data_path": "data/synthetic_dataset.parquet",
  "n_training_rows": 400,
  "n_test_rows": 100,
  "feature_columns": ["benford_chi_square_1h", "benford_mad_1h", ...],
  "feature_schema_hash": "sha256:<hash-of-sorted-feature-column-list>",
  "model_names": ["random_forest", "xgboost", "lightgbm"],
  "python_version": "3.11.9",
  "ledgerlens_version": "0.2.0"
}
```

The `feature_schema_hash` is the SHA-256 of the sorted, newline-joined feature column names. This allows `RiskScorer` to detect schema mismatches at load time.

**`detection/model_inference.py`**:
- In `RiskScorer._load_models()`, after loading `.joblib` files, load `model_metadata.json` (if present) and compute the current feature schema hash from the feature row passed to `score()`.
- If the hashes differ, raise a `RuntimeError` with a clear message explaining which columns are present in the model but missing from the current feature row (and vice versa), rather than silently producing wrong scores.
- Expose the loaded metadata as `RiskScorer.metadata` (a dict or dataclass) so callers and the API can surface "model trained at" timestamps.

**`save_metrics_report`** in `model_training.py`:
- Rename to `save_training_artifacts` and have it write both `metrics.json` and `model_metadata.json`.

---

## Requirements

### Functional
- `model_metadata.json` is written on every `python -m detection.model_training` run.
- `RiskScorer` raises `RuntimeError` (not a silent wrong score) when the loaded model's `feature_schema_hash` does not match the feature row passed to `score()`.
- `RiskScorer.metadata` is `None` when no `model_metadata.json` exists (backward compatibility with pre-versioning model dirs).
- The `--model-dir` CLI flag in `model_training.py` controls where `model_metadata.json` is written, consistent with where `.joblib` files are written.

### Security
- `data_path` in the metadata is the raw CLI argument value. If this path contains credentials or sensitive information (e.g. a presigned S3 URL), it is logged and stored. Add a note in the code comment warning contributors about this.

### Documentation
- Document the `model_metadata.json` schema in `README.md` under a new "Model Artifacts" subsection.
- Update `scripts/README.md` to note that `generate_synthetic_dataset.py` + `model_training.py` now also produce `model_metadata.json`.

---

## Tests Required (mandatory — all must pass)

Add tests to `tests/test_model_training.py` and `tests/test_inference_shap.py` (expand existing files):

1. **`test_save_training_artifacts_writes_metadata`** — after calling the training pipeline against the synthetic dataset, assert `model_metadata.json` exists in `MODEL_DIR` and contains `feature_schema_hash`, `trained_at`, and `feature_columns`.
2. **`test_metadata_feature_hash_matches_training_columns`** — load `model_metadata.json` and independently compute `sha256` of the sorted training feature columns; assert they match.
3. **`test_risk_scorer_exposes_metadata`** — after training, instantiate `RiskScorer` and assert `scorer.metadata["trained_at"]` is a non-empty string and `scorer.metadata["feature_columns"]` is a list.
4. **`test_risk_scorer_raises_on_schema_mismatch`** — write a `model_metadata.json` with a deliberately wrong `feature_schema_hash`; assert `RiskScorer.score()` raises `RuntimeError` containing the word "schema".
5. **`test_risk_scorer_metadata_none_without_metadata_file`** — remove `model_metadata.json` from the model dir; assert `scorer.metadata` is `None` and scoring still works (backward compatibility).
6. **`test_metadata_backward_compat_no_raise_without_file`** — same as above but assert no exception is raised during `_load_models()` when the file is absent.

Run with: `pytest tests/test_model_training.py tests/test_inference_shap.py -v`

All six tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python ML engineering / MLOps. Familiarity with `scikit-learn`, `joblib`, and model serialization practices is required. Experience with model versioning systems (MLflow, DVC, or custom) is a plus.

When commenting to claim this issue, please include:
- Your experience with ML model lifecycle management.
- Whether you have read `detection/model_training.py` and `detection/model_inference.py` in full.
- Any prior work on model versioning, A/B testing infrastructure, or ML deployment pipelines.

This issue directly reduces the risk of silent score regressions caused by model/feature-schema drift — a critical MLOps gap in the current pipeline.
