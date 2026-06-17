# scripts/

## `generate_synthetic_dataset.py`

Generates a synthetic labelled feature matrix for local training, demos,
and tests, without needing live Stellar Horizon data.

The output schema matches `detection/feature_engineering.py::build_feature_matrix`
(`wallet` + all Benford / trade-pattern / volume-timing / wallet-graph
feature columns), plus a `label` column (`1` = wash-trading-like, `0` =
legitimate). Roughly half the rows are generated with "legitimate"
distributions and half with "wash-trading-like" distributions, then
shuffled.

### Usage

```bash
python -m scripts.generate_synthetic_dataset \
    --n-wallets 500 \
    --seed 42 \
    --output data/synthetic_dataset.parquet
```

| Flag | Default | Description |
|---|---|---|
| `--n-wallets` | `500` | Number of synthetic wallet rows to generate |
| `--seed` | `42` | Random seed (controls both data generation and the final shuffle) |
| `--output` | `data/synthetic_dataset.parquet` | Output parquet path |

### Training on the generated dataset

```bash
python -m detection.model_training --data-path data/synthetic_dataset.parquet
```

This trains every model in `MODEL_REGISTRY` (Random Forest, XGBoost,
LightGBM) with SMOTE-balanced training data, writes the fitted models to
`config.MODEL_DIR`, and writes both `metrics.json` (AUC-ROC / PR-AUC / F1
per model) and `model_metadata.json` (feature schema fingerprint and
training metadata) alongside them.

## `score_wallet.py`

Scores a single wallet on a single asset pair on demand, printing the full
RiskScore plus the top-5 SHAP feature attributions to stdout. Useful for
targeted investigations or testing.

### Usage

```bash
python -m scripts.score_wallet \
  --wallet GABC1234... \
  --pair "USDC:GA5Z.../XLM:native" \
  --since 2024-01-01
```

| Flag | Description |
|---|---|
| `--wallet` | Stellar wallet public key (G...) |
| `--pair` | Asset pair to score (e.g. `USDC:GA5Z.../XLM:native`) |
| `--since` | ISO date to start loading trades from |
| `--no-orderbook` | Skip loading order-book events |
| `--json` | Output result as a machine-parseable JSON object |

### Output Example (Human-readable)

```text
Wallet:   GABC1234...
Pair:     USDC:GA5Z.../XLM:native
Score:    83  [FLAGGED]
Benford:  True
ML:       True (confidence 76)

Top 5 SHAP contributors:
  1. benford_mad_24h          +0.34  (value: 0.047)
  2. counterparty_concentration_ratio  +0.29  (value: 0.98)
  ...
```
