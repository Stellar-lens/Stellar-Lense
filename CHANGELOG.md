# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Unified exactly-once dedup/idempotency library (`pipeline/exactly_once.py`)
  replacing the Kafka worker's and trade ingestion's independent, fail-open
  Redis dedup caches. Fixes a critical bug where a crash mid-processing (e.g.
  `AlertDispatcher.dispatch` raising for the second wallet in a trade) could
  cause a redelivered message to be misclassified as a duplicate and its
  offset committed without reprocessing, silently dropping a wallet's score.
  The new caches are fail-closed: a Redis outage raises
  `DedupBackendUnavailableError` instead of allowing all events through.
  `FeatureBuffer.update()` is now idempotent per `(wallet, trade_id)`.
  `AuditMerkleChain` now persists and rehydrates leaf content so a process
  restart no longer looks like tampering (`TamperDetectedError`). Adds a
  `finality` marker (`provisional`/`final`) to `RiskScoreRecord`, and an
  `AlertDeliveryLedger` + `validation.reconciliation.reconcile_alert_delivery`
  to trace every alert-eligible score to a delivered/dead-lettered/suppressed
  outcome. See `docs/adr/0001-unified-idempotency-finality.md`.
  Migrations `0005` (audit Merkle leaf content) and `0006` (risk-score
  finality). New config: `WORKER_HEALTH_STALE_THRESHOLD_SECONDS`.
- Typed exceptions for ingestion and validation failures: a `LedgerLensError`
  base (`utils/exceptions.py`) and the ingestion taxonomy
  (`ingestion/exceptions.py`): `IngestionError` with `InvalidInputError`,
  `RecordValidationError`, `SchemaValidationError`, and
  `SourceUnavailableError`. Failures carry `source` / `reason` / `raw`
  context mirroring the Kafka dead-letter envelope. Adopted across
  `ingestion/`; degraded-mode behaviour (rate limiter, batch account loads,
  metadata cache) is unchanged. Documented in `docs/ingestion.md` under
  "Error handling".
- Cryptographically committed forensic audit trail (`detection/audit_trail.py`):
  signed NDJSON append-only log for report scores, feature/SHAP hashes, and model
  version; `scripts/verify_audit_trail.py` for regulator verification.
  Config: `AUDIT_LOG_PATH`, `AUDIT_VERIFY_PUBLIC_KEY_PATH`.

### Changed
- `ingestion.payment_path_analyzer.reconstruct_path_flow` raises
  `RecordValidationError` instead of `KeyError` when required fields are
  missing. `RecordValidationError` is deliberately not a `KeyError` subclass,
  so callers relying on `except KeyError` here must be updated.

### Fixed
- `scripts/replay_stream.py --resume` now actually seeks to the replay
  consumer group's committed offset per partition — it previously
  unconditionally seeked to the beginning of the topic, silently discarding
  all prior replay progress on every `--resume` invocation. Offsets now
  commit per-message, scoped to that message's exact offset; a persistence
  failure halts the replay run instead of being silently swallowed.
- `migrations/runner.py::MigrationRunner.upgrade(target=...)` no longer
  drops migrations beyond `target` from its returned status report.

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
