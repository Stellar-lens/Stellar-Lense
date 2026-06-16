# Add `--dry-run` Flag to `run_pipeline.py`

**Label:** `good first issue` | `enhancement` | `cli`
**Difficulty:** Good First Issue
**Area:** Pipeline CLI / `run_pipeline.py`

---

## Summary

`run_pipeline.py` currently always writes to the database and (optionally) submits scores on-chain when run. There is no way to preview what the pipeline would flag without actually committing anything to storage. This makes it risky to test configuration changes or inspect results on new asset pairs without side effects.

Add a `--dry-run` flag that runs every pipeline stage — ingestion, feature engineering, and scoring — but suppresses all writes: no rows are upserted to `RISK_SCORE_DB_URL` and no on-chain submissions are made. Flagged wallets are still printed to stdout so the operator can validate behaviour before committing.

---

## Detailed Description

### Current behaviour

Running `python run_pipeline.py` always:
1. Upserts `RiskScore` records to the database via `RiskScoreStore.upsert()` (unless `--no-persist` is already set).
2. Submits flagged wallets on-chain when `--submit-onchain` is passed.

There is no single "read-only preview" mode.

### Required change

Add `--dry-run` as a boolean flag to `parse_args()` in `run_pipeline.py`:

```python
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Run all pipeline stages but skip all writes (DB persist and on-chain submission).",
)
```

When `--dry-run` is set:
- Persistence must be skipped regardless of `--no-persist` (i.e. `--dry-run` implies `--no-persist`).
- On-chain submission must be skipped regardless of `--submit-onchain`.
- A clearly visible log line must be emitted at startup: `[DRY RUN] No data will be written.`
- Flagged wallets must still be printed to stdout exactly as they are in the normal run.

### Files to modify

| File | Change |
|---|---|
| `run_pipeline.py` | Add `--dry-run` to `parse_args()`; gate persist and submit calls behind `not args.dry_run` |

No other files require modification.

---

## Requirements

### Functional
- `--dry-run` suppresses all database writes and all on-chain contract calls.
- `--dry-run` is compatible with all other flags (`--since`, `--no-orderbook`, `--submit-onchain`). When combined with `--submit-onchain`, both flags are accepted but the submit step is silently skipped (log a warning to make this explicit).
- The dry-run log banner must appear before stage 1 so it is the first meaningful line of output.

### Security
- No credentials (`LEDGERLENS_SUBMITTER_SECRET`) should be validated or loaded during a dry run; the contract client must not be instantiated.

### Documentation
- Update the flag table in `README.md` under `run_pipeline.py flags` to include `--dry-run`.

---

## Tests Required (mandatory — all must pass)

Add the following tests to a new file `tests/test_dry_run.py` or inside the existing `tests/test_pipeline.py` (if one is created):

1. **`test_dry_run_skips_persist`** — patch `RiskScoreStore.upsert` and assert it is **never** called when `--dry-run` is passed.
2. **`test_dry_run_skips_submit_onchain`** — patch `LedgerLensContractClient.submit_score` and assert it is **never** called even when both `--dry-run` and `--submit-onchain` are passed together.
3. **`test_dry_run_still_prints_flagged`** — assert that flagged wallets are still logged (captured via `caplog` or stdout capture) when `--dry-run` is active.
4. **`test_dry_run_log_banner`** — assert that the `[DRY RUN]` banner appears in log output when the flag is set.

Run with: `pytest tests/test_dry_run.py -v`

All four tests must pass. `make lint` and `make test` must also pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python backend / CLI tooling. No ML or blockchain knowledge required.

When commenting to claim this issue, please include:
- Your Python experience level (junior / mid / senior).
- Whether you have read through `run_pipeline.py` and `utils/logging.py` so you understand the existing logger setup.
This is an excellent entry point for new contributors: the change is small, self-contained, and teaches you the overall pipeline structure without requiring deep ML or Stellar/Soroban knowledge.
