# Implement Per-Pair Feature Attribution in the Detection Pipeline

**Label:** `intermediate` | `enhancement` | `detection` | `pipeline`
**Difficulty:** Intermediate
**Area:** `run_pipeline.py`, `detection/feature_engineering.py`, `detection/risk_score_store.py`

> **Blocks:** Issue #014 (Cross-Asset Coordinated Wash Trade Detection) depends on per-pair trade filtering being in place before cross-pair features can be computed. Merge this issue before starting #014.

---

## Summary

The pipeline currently loads trades from all `WATCHED_ASSET_PAIRS`, merges them into a single DataFrame, and builds **one combined feature matrix** across all pairs. The `asset_pair` key stored in `RiskScore` records is a concatenated label (`watched_pairs_label()`) like `"USDC:GA5Z.../XLM:native+BTC:GCCD.../XLM:native"` — not a per-pair attribution.

This is a known gap documented in `README.md` (§ "Known gaps / TODOs") and in `run_pipeline.py:13`:
> `run_pipeline.py`'s persisted `asset_pair` is a combined label across all `WATCHED_ASSET_PAIRS` (`watched_pairs_label()`), not a per-pair attribution.

As a result:
- The `ledgerlens-api` endpoint `/score/{wallet}/{pair}` cannot distinguish a wallet's risk on `USDC/XLM` from its risk on `BTC/XLM`.
- Risk scores are inflated or diluted by cross-pair trade volume.
- SHAP explanations are meaningless when feature rows mix trades from unrelated pairs.

This issue asks you to refactor the pipeline to build a **separate feature matrix per asset pair** and store one `RiskScore` record per `(wallet, asset_pair)` tuple.

---

## Detailed Description

### Root cause

`load_watched_pairs_to_dataframe` returns a single combined DataFrame. `build_feature_matrix` iterates over all wallets found in the entire frame. There is no filtering by pair before feature computation.

### Required architecture change

1. **`ingestion/historical_loader.py`** — Add `load_pair_to_dataframe(base_asset, counter_asset, start_time)` as a single-pair variant of `load_watched_pairs_to_dataframe`. The existing combined loader should call this internally.

2. **`run_pipeline.py`** — Change stage 1 to load trades **per pair** into a `dict[str, pd.DataFrame]` keyed by the canonical `pair_id` string (`CODE:ISSUER/XLM:native`). Iterate the dict in stages 2–4, building a feature matrix and scoring wallets **per pair**, then upsert one record per `(wallet, pair_id)` to the store.

3. **`detection/feature_engineering.py`** — No structural change required; `build_feature_matrix` already works on an arbitrary DataFrame. The change is that the caller now filters by pair before passing the frame.

4. **`detection/risk_score_store.py`** — No change required; `RiskScoreStore.upsert` already takes `wallet` + `asset_pair` as separate arguments.

5. **`run_pipeline.py::watched_pairs_label()`** — This function and its usage should be removed once per-pair attribution is complete.

### Backward compatibility

The `RiskScoreRecord` schema in `detection/persistence.py` already stores `asset_pair` as a free string with a `UNIQUE(wallet, asset_pair)` constraint — no schema migration is needed as long as new records use the canonical `pair_id` format.

---

## Requirements

### Functional
- One `RiskScore` record per `(wallet, pair_id)` is upserted to the database per pipeline run.
- A wallet that trades on two different pairs gets two separate records, each scored using only that pair's trades.
- `--no-orderbook` and `--submit-onchain` must continue to work correctly with the per-pair loop.
- Logging should clearly indicate which pair is currently being processed at each stage.

### Performance
- Pairs must be processed sequentially (concurrent pair loading can be addressed in a separate issue). The total runtime increase from sequential multi-pair loading is acceptable.

### Security
- No change to credential handling.

### Documentation
- Remove the "Known gaps" bullet for per-pair attribution from `README.md`.
- Update the "Shared Contracts" section to confirm the `asset_pair` format is now enforced as `CODE:ISSUER/CODE:ISSUER` everywhere.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_per_pair_pipeline.py`:

1. **`test_load_pair_to_dataframe_filters_correctly`** — mock `_fetch_page` to return trades for two different pairs; assert `load_pair_to_dataframe` for pair A returns only pair A's trades.
2. **`test_feature_matrix_built_per_pair`** — provide two separate trade DataFrames (one per pair) and assert `build_feature_matrix` returns distinct wallets/feature values for each.
3. **`test_pipeline_upserts_one_record_per_wallet_per_pair`** — using a test SQLite in-memory DB, run the pipeline main loop over two pairs with two wallets each; assert the `risk_scores` table contains `wallet_count × 2` rows, each with a distinct `(wallet, asset_pair)` tuple.
4. **`test_watched_pairs_label_removed`** — confirm `watched_pairs_label` is no longer called (import it and assert it raises `ImportError` or verify it's deleted from `run_pipeline.py`).
5. **`test_per_pair_logging`** — use `caplog` to assert that the pair `pair_id` string appears in log output during stage 1 iteration.

Run with: `pytest tests/test_per_pair_pipeline.py -v`

All five tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python backend / data pipeline engineering. Familiarity with `pandas`, `SQLAlchemy`, and multi-step ETL pipelines is required. No Stellar SDK or ML expertise is needed.

When commenting to claim this issue, please include:
- Your experience with Python data pipeline refactoring.
- Whether you have read `run_pipeline.py`, `ingestion/historical_loader.py`, and `detection/feature_engineering.py` in full.
- Any prior work on pipeline architecture or ETL systems.

This is a non-trivial architectural refactor that fixes a documented known gap and directly unblocks the API layer's per-pair score endpoint. It is a meaningful contribution with real downstream impact.
