# stellar-lense-core

The detection engine behind Stellar Lense: pulls trades from Stellar Horizon
and scores wallets for wash-trading risk with Benford's Law analysis plus
trade-pattern heuristics. `apps/api` imports it; it has no server of its own.

## Modules

| Module | What it does |
|---|---|
| `ingestion/historical_loader.py` | Pages Horizon `/trades` for an asset pair back to a lookback cutoff and returns a DataFrame. |
| `ingestion/trade_parser.py` | Converts a raw Horizon trade record into a validated `Trade`. |
| `ingestion/http_client.py` | Horizon HTTP client: rate limiting, retries with capped back-off, Horizon version guard. |
| `ingestion/data_models.py` | Pydantic models for trades, assets and related Horizon records. |
| `ingestion/synthetic_data.py` | Seeded synthetic wash/organic trade generator (tests and the demo model). |
| `detection/benford_engine.py` | Benford first-digit statistics: chi-square, Z-scores, MAD, KS/Kuiper, bootstrap p-values, per-pair strata. |
| `detection/feature_engineering.py` | Per-wallet features: Benford windows, counterparty concentration, round trips, self-matching, timing, centrality. |
| `detection/risk_score.py` | The `RiskScore` record shared with the API. |
| `detection/shap_explainer.py` | SHAP attributions for the optional ML model. |

## Development

From the repository root:

```bash
uv run --package stellar-lense-core --extra test pytest packages/core/tests
cd packages/core && uvx ruff@0.4.10 check .
```

## What used to be here

Until the consolidation pass, this package also contained a 70-route local
API (REST, gRPC, GraphQL, WebSockets), federated learning, ZK range proofs and
circom circuits, GNN and temporal models, causal inference, cross-chain
(EVM/Solana) loaders, Go/TypeScript/Rust SDKs, Helm charts and chaos
experiments. None of it was called by the shipped product, so it was moved
off `main`. It is preserved, unchanged, on the `archive/pre-consolidation`
branch and the `archive-pre-consolidation` tag.
