# Implement AccountActivity Ingestion Loader to Wire Wallet Funding Graph into the Pipeline

**Label:** `intermediate` | `enhancement` | `ingestion` | `detection`
**Difficulty:** Intermediate
**Area:** `ingestion/`, `detection/wallet_graph.py`, `run_pipeline.py`

---

## Summary

`detection/wallet_graph.py` implements `build_funding_graph`, `funding_source_similarity`, and `network_centrality` — three features that detect sock-puppet / wash-trading rings by analysing which accounts share the same funding source. These features are **wired into the feature vector** in `detection/feature_engineering.py::compute_wallet_graph_features`, but they **always return `0.0`** in production because no ingestion source for `AccountActivity.funding_account` data exists.

This is documented as a known gap in `README.md`:
> Wallet funding-graph features (`funding_source_similarity`, `network_centrality`) are implemented in `detection/wallet_graph.py`, but `run_pipeline.py` doesn't build a `funding_graph` yet — there's no ingestion source for `AccountActivity.funding_account` data.

This issue asks you to implement an `AccountActivity` loader that reads account creation and funding data from Horizon, and to wire it into `run_pipeline.py` so the funding graph is built and passed to `build_feature_matrix`.

---

## Detailed Description

### Horizon data source

The Stellar Horizon API exposes account creation events via the **effects endpoint**:

```
GET /accounts/{account_id}/effects?type=account_created
```

The `account_created` effect record includes:
- `account` — the new account's public key.
- `funder` — the funding account's public key (the one that performed `create_account`).
- `created_at` — the ledger timestamp of the creation.

### What to implement

**`ingestion/account_activity_loader.py`** (new file):
- `load_account_activity(account_id: str) -> AccountActivity | None` — fetch the `account_created` effect for a single account and return an `AccountActivity` instance (already defined in `ingestion/data_models.py`), or `None` if the account has no creation record on Horizon.
- `load_accounts_activity(account_ids: list[str]) -> list[AccountActivity]` — batch-fetch `AccountActivity` for a list of accounts. Apply the existing `retry_with_backoff` decorator from `utils/retry.py`.

**`run_pipeline.py`**:
- After loading order-book events (stage 2), add a new stage that calls `load_accounts_activity(wallets)` and passes the result to `detection.wallet_graph.build_funding_graph`.
- Pass the resulting `funding_graph` to `build_feature_matrix`.
- Add a `--no-graph` flag (analogous to `--no-orderbook`) to skip this stage for faster runs.

### Horizon API shape

```json
{
  "type": "account_created",
  "account": "GCONTRIBUTORABC...",
  "funder": "GFUNDINGACCOUNTXYZ...",
  "created_at": "2024-01-15T10:30:00Z",
  "starting_balance": "1.0000000"
}
```

Map `account` → `AccountActivity.account_id`, `funder` → `AccountActivity.funding_account`, `created_at` → `AccountActivity.account_created_at`.

---

## Requirements

### Functional
- `load_account_activity` must return `None` (not raise) when an account has no `account_created` effect (e.g. genesis accounts, accounts created before the effect endpoint's history window).
- `load_accounts_activity` must tolerate individual account lookup failures (log a warning, continue with remaining accounts).
- The `--no-graph` flag must completely skip account activity loading and funding graph construction; `funding_source_similarity` and `network_centrality` remain `0.0`.
- When the funding graph is built and passed to `build_feature_matrix`, those two features must reflect real graph values, not `0.0`.

### Performance
- Account activity loading is sequential per account. This is acceptable for v1; concurrent loading is a separate issue.

### Security
- No credentials required for Horizon account effects reads (public endpoint).

### Documentation
- Remove the relevant "Known gaps" bullet from `README.md`.
- Add `--no-graph` to the flag table in `README.md`.
- Document `account_activity_loader.py` in the Repository Structure section of `README.md`.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_account_activity_loader.py`:

1. **`test_load_account_activity_returns_model`** — mock `Server.accounts().for_account().order().call()` to return a fake `account_created` effect; assert the returned `AccountActivity` has the correct `account_id`, `funding_account`, and `account_created_at`.
2. **`test_load_account_activity_returns_none_for_missing_account`** — mock the effect response with an empty record list; assert `None` is returned without raising.
3. **`test_load_accounts_activity_batches_correctly`** — mock responses for three accounts; assert all three `AccountActivity` objects are returned.
4. **`test_load_accounts_activity_tolerates_individual_failure`** — mock one account to raise `ConnectionError`; assert the other two are still returned.
5. **`test_funding_graph_features_nonzero_when_graph_provided`** — build a small `AccountActivity` list with two wallets sharing a funder; assert `funding_source_similarity > 0` and `network_centrality > 0` in the resulting feature vector.
6. **`test_pipeline_no_graph_flag_skips_activity_load`** — patch `load_accounts_activity` and assert it is **never called** when `--no-graph` is passed to the pipeline.

Run with: `pytest tests/test_account_activity_loader.py -v`

All six tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python backend / Stellar Horizon API. Knowledge of the Stellar Horizon REST API and `stellar_sdk` Python library is strongly preferred. Familiarity with `networkx` is helpful.

When commenting to claim this issue, please include:
- Your experience with the Stellar Horizon API or other blockchain data APIs.
- Whether you have read `ingestion/orderbook_loader.py` (a closely analogous loader) and `detection/wallet_graph.py` in full.
- Whether you have used `stellar_sdk` or similar SDK libraries in past projects.

This issue activates two currently-zero features that significantly improve wash-trading-ring detection. It is a meaningful contribution with direct impact on detection quality.
