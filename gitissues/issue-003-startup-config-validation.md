# Add Startup Validation for Required Configuration Values in `config.py`

**Label:** `good first issue` | `enhancement` | `config`
**Difficulty:** Good First Issue
**Area:** `config.py` / startup guardrails

---

## Summary

`config.py` loads all configuration from environment variables with silent defaults. When required values such as `WATCHED_ASSET_PAIRS` or `RISK_SCORE_DB_URL` are missing or malformed, the pipeline fails deep inside the ingestion or persistence layer with cryptic errors (e.g. `ValueError: WATCHED_ASSET_PAIRS is not configured` thrown from `stream_all_watched_pairs`, or a SQLAlchemy error at first DB write).

This issue asks for an explicit `validate()` method on the `Config` class that checks all required values at import time (or at pipeline startup) and raises a clear, human-readable `EnvironmentError` listing every misconfigured variable — not just the first one.

---

## Detailed Description

### Current behaviour

`Config` is a plain class with class-level attributes. There is no validation step. Operators who miss a required env var only discover the problem when the pipeline crashes mid-run, often after several minutes of trade ingestion.

### Required change

Add a `validate()` classmethod to `Config` that:
1. Checks `WATCHED_ASSET_PAIRS` is non-empty.
2. Checks `RISK_SCORE_DB_URL` is a non-empty string.
3. Checks `MODEL_DIR` is a non-empty string.
4. When `--submit-onchain` mode is relevant (detect via an optional `require_onchain: bool` parameter), additionally checks that `LEDGERLENS_CONTRACT_ID` and `LEDGERLENS_SUBMITTER_SECRET` are both set.
5. Collects **all** failures and raises a single `EnvironmentError` listing each missing/invalid variable, rather than failing on the first one.

Call `config.validate()` at the top of `run_pipeline.py::main()`, before any ingestion begins.

Example error message:
```
EnvironmentError: LedgerLens configuration errors:
  - WATCHED_ASSET_PAIRS is not set. Set it to a comma-separated list like "USDC:GA5Z...,BTC:GCCD..."
  - RISK_SCORE_DB_URL is not set. Defaults to sqlite:///ledgerlens.db if omitted intentionally.
```

### Files to modify

| File | Change |
|---|---|
| `config.py` | Add `validate(require_onchain=False)` classmethod |
| `run_pipeline.py` | Call `config.validate(require_onchain=args.submit_onchain)` at the top of `main()` |

---

## Requirements

### Functional
- `validate()` must collect **all** errors before raising — do not short-circuit on the first failure.
- `validate()` must not raise when all required values are present.
- The error message must name each misconfigured variable and suggest what value to provide.
- `LEDGERLENS_CONTRACT_ID` and `LEDGERLENS_SUBMITTER_SECRET` are only required when `require_onchain=True`; they must not cause validation failures in normal (off-chain) mode.

### Security
- `LEDGERLENS_SUBMITTER_SECRET` must not be echoed in any log or error message. The validation check should confirm the variable is **set and non-empty**, not print its value.

### Documentation
- Add a short "Configuration" section to `README.md` listing required vs. optional env vars and their defaults (the `.env.example` file already exists but is not referenced from the README).

---

## Tests Required (mandatory — all must pass)

Add the following tests to `tests/test_config_validation.py`:

1. **`test_validate_passes_with_required_vars_set`** — set `WATCHED_ASSET_PAIRS`, `RISK_SCORE_DB_URL`, and `MODEL_DIR` via `monkeypatch.setenv`; assert `Config.validate()` returns without raising.
2. **`test_validate_raises_when_pairs_missing`** — with `WATCHED_ASSET_PAIRS=""`, assert `EnvironmentError` is raised and `"WATCHED_ASSET_PAIRS"` appears in the message.
3. **`test_validate_raises_multiple_errors_at_once`** — clear both `WATCHED_ASSET_PAIRS` and `RISK_SCORE_DB_URL`; assert the raised `EnvironmentError` message mentions **both** variable names.
4. **`test_validate_onchain_requires_contract_vars`** — when `require_onchain=True` and `LEDGERLENS_CONTRACT_ID=""`, assert `EnvironmentError` is raised naming `LEDGERLENS_CONTRACT_ID`.
5. **`test_validate_secret_not_in_error_message`** — set `LEDGERLENS_SUBMITTER_SECRET="SXXXXXX"` but clear `LEDGERLENS_CONTRACT_ID`; assert the error message does **not** contain `"SXXXXXX"`.

Run with: `pytest tests/test_config_validation.py -v`

All five tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python backend / configuration management. No ML or Stellar/Soroban knowledge required.

When commenting to claim this issue, please include:
- Your familiarity with Python `os.getenv` and `dotenv`.
- Whether you have read both `config.py` and `run_pipeline.py`.
- Any prior experience writing startup-time validation in Python services.

This is a well-scoped beginner issue that has a real operational impact: clear config errors save operators hours of debugging.
