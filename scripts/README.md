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
`config.MODEL_DIR`, and writes `metrics.json` (AUC-ROC / PR-AUC / F1 per
model) alongside them.
