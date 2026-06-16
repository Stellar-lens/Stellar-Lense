# Add `score-wallet` CLI Command for On-Demand Single-Wallet Scoring

**Label:** `intermediate` | `enhancement` | `cli` | `detection`
**Difficulty:** Intermediate
**Area:** new `scripts/score_wallet.py`, `detection/model_inference.py`, `detection/shap_explainer.py`

---

## Summary

The only way to score a wallet today is to run the full `run_pipeline.py`, which loads trade history for **all** watched asset pairs before computing a single score. This is impractical for:
- Operators who want to quickly investigate a suspicious wallet flagged by an alert.
- API developers testing the scoring logic against a specific wallet/pair.
- Analysts who need to re-score a wallet after a manual data correction.

This issue asks you to implement a `scripts/score_wallet.py` CLI that scores a **single wallet on a single asset pair** on demand, printing the full `RiskScore` plus the top-5 SHAP feature attributions to stdout.

---

## Detailed Description

### Usage

```bash
python -m scripts.score_wallet \
  --wallet GABC1234... \
  --pair "USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN" \
  --since 2024-01-01 \
  [--no-orderbook] \
  [--json]
```

### Pipeline stages (single-wallet)

1. Load historical trades for the wallet on the specified asset pair using `ingestion/historical_loader.py`.
2. Load order-book events for the wallet using `ingestion/orderbook_loader.py` (unless `--no-orderbook`).
3. Build the wallet's feature vector using `detection/feature_engineering.py::build_feature_vector`.
4. Score the feature row using `detection/model_inference.py::RiskScorer`.
5. Compute SHAP explanations using `detection/shap_explainer.py::ShapExplainer.explain_ensemble`.
6. Print result to stdout. With `--json`, print a JSON object; without it, print a human-readable table.

### Output format (human-readable)

```
Wallet:   GABC1234...
Pair:     USDC:GA5Z.../XLM:native
Score:    83  [FLAGGED]
Benford:  True (MAD 0.047 at 24h window)
ML:       True (confidence 76)

Top 5 SHAP contributors:
  1. benford_mad_24h          +0.34  (value: 0.047)
  2. counterparty_concentration_ratio  +0.29  (value: 0.98)
  3. round_trip_frequency     +0.21  (value: 0.41)
  4. benford_chi_square_168h  +0.18  (value: 45.2)
  5. account_age_days         -0.12  (value: 3.0)
```

### Output format (JSON, `--json` flag)

```json
{
  "wallet": "GABC1234...",
  "asset_pair": "USDC:GA5Z.../XLM:native",
  "score": 83,
  "benford_flag": true,
  "ml_flag": true,
  "confidence": 76,
  "shap_explanations": [
    {"feature": "benford_mad_24h", "contribution": 0.34, "value": 0.047},
    ...
  ]
}
```

### Files to create / modify

| File | Action |
|---|---|
| `scripts/score_wallet.py` | New file — full single-wallet scoring CLI |
| `scripts/README.md` | Document new script |
| `README.md` | Add `score-wallet` under "Quick Start" |

No changes to `detection/` or `ingestion/` modules — reuse existing public functions.

---

## Requirements

### Functional
- The script must exit with code `0` on success, `1` on error (missing models, invalid wallet ID, Horizon unreachable).
- `--json` output must be valid JSON parseable by `jq`.
- Without `--json`, the output must be human-readable with score highlighted as `[FLAGGED]` if `score >= RISK_SCORE_FLAG_THRESHOLD`, or `[OK]` otherwise.
- When trained models do not exist in `MODEL_DIR`, print a clear error message suggesting `python -m detection.model_training` and exit with code `1`.
- `--since` accepts an ISO date string (same parsing as `run_pipeline.py`).

### Security
- The wallet ID format must be validated as a 56-character Stellar public key (`G` prefix, base32). Reject invalid formats with a clear error before making any Horizon calls.

### Documentation
- Add the script to `scripts/README.md` with a full usage example.
- Add `score-wallet` to the "Quick Start" section of `README.md`.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_score_wallet.py`:

1. **`test_score_wallet_outputs_score_and_shap`** — mock Horizon trade/operation fetches and the trained model; invoke `scripts.score_wallet.main()` with a valid wallet and pair; assert the string output contains `Score:`, `Benford:`, and `Top 5 SHAP`.
2. **`test_score_wallet_json_output_is_valid_json`** — same mock setup with `--json`; assert `json.loads(output)` succeeds and contains all required keys.
3. **`test_score_wallet_flagged_label`** — mock the scorer to return `score=85`; assert `[FLAGGED]` appears in human-readable output.
4. **`test_score_wallet_ok_label`** — mock the scorer to return `score=30`; assert `[OK]` appears in human-readable output.
5. **`test_score_wallet_invalid_wallet_id_exits_1`** — pass `--wallet BADID` and assert the process exits with code `1` and prints a validation error.
6. **`test_score_wallet_missing_models_exits_1`** — point `MODEL_DIR` at an empty directory; assert exit code `1` and a suggestion to run `model_training.py` appears in stderr.

Run with: `pytest tests/test_score_wallet.py -v`

All six tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python CLI / backend. Familiarity with `argparse`, `json`, and the existing `detection/` and `ingestion/` module APIs. Stellar wallet address format knowledge is a plus.

When commenting to claim this issue, please include:
- Your experience building Python CLI tools.
- Whether you have read `run_pipeline.py`, `detection/model_inference.py`, and `detection/shap_explainer.py`.
- Whether you have run the existing pipeline locally or with the synthetic dataset.

This is an operator-experience improvement that makes the detection engine practical for real investigation workflows, not just batch scoring.
