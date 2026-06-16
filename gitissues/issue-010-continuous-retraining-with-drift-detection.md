# Implement Automated Continuous Retraining Pipeline with Feature Drift Detection

**Label:** `advanced` | `mlops` | `detection` | `pipeline`
**Difficulty:** Advanced
**Area:** `detection/`, `scripts/`, `run_pipeline.py`, CI/CD

> **Depends on:** Issue #006 (Model Versioning and Stale Model Detection) must be merged first. This issue's drift monitor reads `model_metadata.json` and `feature_schema_hash` introduced in #006. Do not start this issue until #006 is merged and `model_metadata.json` is being produced by the training pipeline.

---

## Summary

The ensemble models are trained once, saved to `MODEL_DIR`, and then used indefinitely. The Stellar DEX market evolves continuously: new wash-trading strategies emerge, asset liquidity shifts, and bot behaviour adapts. A model trained on data from six months ago will progressively degrade as the underlying distribution drifts.

Currently, there is no mechanism to:
- Detect when the feature distribution has drifted away from the training distribution.
- Trigger retraining automatically when drift is detected.
- Safely promote a newly retrained model to production without corrupting the currently live model.
- Track model performance over time.

This issue asks you to design and implement a **drift detection system** and a **safe automated retraining workflow** within this repository.

---

## Detailed Description

### Part 1: Feature drift monitor (`detection/drift_monitor.py`)

Implement a `DriftMonitor` class that compares the current production feature distribution against the training-time distribution using the **Population Stability Index (PSI)** — the industry standard metric for detecting feature drift in tabular ML systems:

```
PSI = Σ (observed_i - expected_i) * ln(observed_i / expected_i)
```

Where `i` iterates over bins of each feature's value distribution.

- PSI < 0.1: no significant drift.
- 0.1 ≤ PSI < 0.25: moderate drift — monitor.
- PSI ≥ 0.25: significant drift — trigger retraining.

The `DriftMonitor` must:
- Accept a **reference distribution** (the training-time feature statistics, saved as `model_metadata.json` per Issue #006) and a **current distribution** (feature matrix from the latest pipeline run).
- Compute PSI for every feature column.
- Return a `DriftReport` dataclass: `{feature: str, psi: float, drift_flag: bool}` per feature, plus an `any_drift_detected: bool` summary field.
- Write the drift report to `reports/drift_report_{timestamp}.json` for audit trail.

### Part 2: Retraining trigger (`scripts/retrain_if_drifted.py`)

A CLI script that:
1. Loads the current production model's reference distribution from `model_metadata.json`.
2. Runs the feature pipeline against recent Horizon data (configurable `--lookback-days`).
3. Calls `DriftMonitor.compute()` to assess drift.
4. If `any_drift_detected=True`, runs the full retraining pipeline against the latest available labelled dataset.
5. Evaluates the new model against a hold-out test set and only promotes it to `MODEL_DIR` if it **improves** (or at least does not degrade) AUC-ROC and F1 relative to the current model's recorded metrics in `metrics.json`.
6. Backs up the old model artifacts to `models/archive/{timestamp}/` before overwriting `MODEL_DIR`.
7. Writes a `reports/retrain_report_{timestamp}.json` with: drift report, old metrics, new metrics, promotion decision, and reason.

### Part 3: GitHub Actions workflow (`.github/workflows/retrain.yml`)

A scheduled workflow (weekly, every Monday at 02:00 UTC) that:
- Installs dependencies.
- Runs `scripts/retrain_if_drifted.py --lookback-days 30`.
- On promotion, commits the new model artifacts and metadata to the repository (or uploads to an artifact store — parameterised via `MODEL_STORE_TYPE` env var).
- Posts a summary comment to the most recent open PR (or creates a tracking issue) with the drift report and promotion decision.

**Security**: The workflow must use GitHub OIDC for artifact store authentication — no long-lived secrets stored in GitHub Actions.

### Part 4: Model archive (`models/archive/`)

- Archive directory structure: `models/archive/{YYYYMMDD_HHMMSS}/`.
- Each archive contains: all `.joblib` files, `metrics.json`, `model_metadata.json`.
- Add a `scripts/list_model_versions.py` CLI that prints a table of archived model versions with their training dates and AUC-ROC/F1 metrics.

---

## Requirements

### Functional
- Drift detection must compute PSI for **all** feature columns independently, not a single aggregate score.
- The promotion gate must require AUC-ROC ≥ old_auc - 0.01 AND F1 ≥ old_f1 - 0.01 (1 percentage point tolerance for stochastic variation). If either metric degrades beyond tolerance, the new model is archived but NOT promoted.
- Archive before every retraining run, even if promotion fails.
- The `retrain_if_drifted.py` script must exit with code `0` (no drift / no retraining needed), `2` (retrained and promoted), or `3` (retrained but NOT promoted — regression detected). Never exit with code `1` except on fatal errors.

### Correctness
- PSI bins must handle zero-frequency bins without `log(0)` errors (use the standard small-constant fix: clip proportions to ≥ 1e-4).
- PSI computation must be validated against a known reference implementation (document the reference in code comments).

### Security
- Archived model directories must be readable only by the pipeline user (chmod 750 or equivalent).
- The GitHub Actions workflow must not hard-code any secrets; use repository secrets and OIDC.

### Documentation
- New `docs/drift_detection.md` explaining: PSI methodology, threshold choices, the promotion gate logic, and how to interpret drift reports.
- Update `README.md` to reference the continuous retraining system.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_drift_monitor.py` and `tests/test_retrain_trigger.py`:

1. **`test_psi_below_threshold_no_drift`** — two identical distributions; assert `psi < 0.1` and `drift_flag = False` for all features.
2. **`test_psi_above_threshold_triggers_drift`** — reference distribution concentrated on low values; current distribution concentrated on high values; assert `psi >= 0.25` and `drift_flag = True` for the shifted feature.
3. **`test_psi_handles_zero_frequency_bins`** — bins where the reference has zero frequency; assert no `ZeroDivisionError` or `log(0)` error.
4. **`test_drift_report_written_to_json`** — run `DriftMonitor.compute()` and assert a JSON file is written to `reports/` with the correct schema.
5. **`test_promotion_gate_blocks_regression`** — mock new model AUC-ROC 0.02 below old AUC-ROC; assert the promotion is rejected and the archive still exists.
6. **`test_promotion_gate_allows_improvement`** — mock new model metrics all above old metrics; assert the `.joblib` files in `MODEL_DIR` are replaced and the archive exists.
7. **`test_archive_created_before_promotion`** — mock a promotion scenario; assert the `models/archive/` directory is populated **before** the production model files are overwritten.
8. **`test_retrain_script_exit_codes`** — assert exit code `0` when no drift, `2` when retrained and promoted, `3` when retrained but not promoted.

Run with: `pytest tests/test_drift_monitor.py tests/test_retrain_trigger.py -v`

All eight tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** MLOps / ML engineering. Deep familiarity with model evaluation metrics (AUC-ROC, F1), drift detection methodology (PSI, KS test, Jensen-Shannon divergence), and CI/CD automation is required. Experience with GitHub Actions and model deployment pipelines is essential.

When commenting to claim this issue, please include:
- Your experience with MLOps and production ML systems.
- Specific tools or frameworks you have used for drift detection (Evidently, Alibi Detect, custom PSI, etc.).
- Whether you have designed or operated a retraining pipeline in production.
- A brief technical proposal for how you would structure the promotion gate (2–3 sentences).

This is one of the most operationally critical advanced issues: without continuous retraining, the detection engine will silently degrade as wash-trading strategies evolve.
