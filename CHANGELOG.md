# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Typed exceptions for ingestion and validation failures: a `LedgerLensError`
  base (`utils/exceptions.py`) and the ingestion taxonomy
  (`ingestion/exceptions.py`): `IngestionError` with `InvalidInputError`,
  `RecordValidationError`, `SchemaValidationError`, and
  `SourceUnavailableError`. Failures carry `source` / `reason` / `raw`
  context mirroring the Kafka dead-letter envelope. Adopted across
  `ingestion/`; degraded-mode behaviour (rate limiter, batch account loads,
  metadata cache) is unchanged. Documented in `docs/ingestion.md` under
  "Error handling".
- `docs/simulator.md`: documents the wash-trade simulators
  (`scripts/wash_trade_simulator.py`,
  `scripts/adversarial_wash_trade_simulator.py`) and the realism evaluation
  (`scripts/evaluate_simulator_realism.py`) — what each generates, what the FFD
  and discriminator-accuracy metrics mean, how to read realism scores, and exact
  generate/evaluate commands.
- `docs/graph_features.md`: added a graph-theory glossary (funding edge,
  ancestor traversal, community, ring, internal edge density, motif,
  reciprocity), each linked to the function that computes it, with the terms
  cross-linked from their first use in the document.
- Cryptographically committed forensic audit trail (`detection/audit_trail.py`):
  signed NDJSON append-only log for report scores, feature/SHAP hashes, and model
  version; `scripts/verify_audit_trail.py` for regulator verification.
  Config: `AUDIT_LOG_PATH`, `AUDIT_VERIFY_PUBLIC_KEY_PATH`.

### Changed
- `ingestion.payment_path_analyzer.reconstruct_path_flow` raises
  `RecordValidationError` instead of `KeyError` when required fields are
  missing. `RecordValidationError` is deliberately not a `KeyError` subclass,
  so callers relying on `except KeyError` here must be updated.

## [0.2.0] - 2026-06-13

### Added
- MIT LICENSE.
- Project tooling: `pyproject.toml` (ruff/black/mypy/pytest config), `Makefile`,
  pre-commit hooks, and CI workflow (lint + test on Python 3.11/3.12).
- `Dockerfile` / `.dockerignore` for containerized runs.
- `CONTRIBUTING.md` with local dev setup and PR guidelines.
- GitHub issue templates (bug report, feature request) and a pull request
  template.
- Structured logging (`utils/logging.py`) and a retry/backoff helper
  (`utils/retry.py`) for Horizon API calls.
- Persistence layer for `RiskScore` records (`detection/persistence.py`,
  `detection/risk_score_store.py`) backed by SQLAlchemy and `RISK_SCORE_DB_URL`.
- Order-book event ingestion (`ingestion/orderbook_loader.py`) and a real
  `order_cancellation_rate` feature.
- Wallet funding-graph features: `funding_source_similarity` and
  `network_centrality` (`detection/wallet_graph.py`).
- Soroban contract client (`integrations/contract_client.py`) for
  `submit_score` / `get_score` against `ledgerlens-score`.
- Synthetic labelled dataset generator (`scripts/generate_synthetic_dataset.py`,
  with usage docs in `scripts/README.md`) and a `model_training.py` CLI for
  local training/demo runs.
- Ensemble SHAP aggregation (`ShapExplainer.explain_ensemble`) and explainer
  caching.
- Test coverage for persistence, order-book ingestion, wallet graph features,
  the contract client, the training CLI, and ensemble inference/SHAP.
- Comprehensive unit tests for `JWTAuthenticator.extract_permissions()` and token verification in `tests/test_ws_auth.py`.

### Changed
- `run_pipeline.py` now loads order-book events, persists scored wallets,
  and supports `--no-orderbook`, `--no-persist`, and `--submit-onchain`
  flags.
- `model_inference.py`'s ensemble combination is now a configurable
  `_combine_probabilities` helper, and `confidence` reflects inter-model
  agreement rather than mirroring `score`.

### Fixed
- `RiskScorer.score` and `ShapExplainer` now coerce feature rows to numeric
  dtypes before calling models/explainers, fixing failures with XGBoost and
  newer SHAP versions.
- `extract_permissions` logic to correctly return `{"scores:read:all"}` when given the unrestricted `"scores:read"` scope.
