# End-to-End Soroban Testnet Integration Tests for On-Chain Score Submission

**Label:** `advanced` | `testing` | `blockchain` | `integrations` | `ci`
**Difficulty:** Advanced
**Area:** `integrations/contract_client.py`, `.github/workflows/ci.yml`, new `tests/integration/`

> **Cross-repo blocker:** This issue requires a compiled `ledgerlens-score` WASM artifact from the [`ledgerlens-contract`](https://github.com/Ledger-Lenz/ledgerlens-contract) repository. Before claiming this issue, confirm that a Testnet-deployable release artifact (`ledgerlens_score.wasm`) is available from that repo's releases page. If no release artifact exists yet, this issue cannot be completed — comment on the issue and the maintainer will coordinate the cross-repo dependency. Do not start implementation until the WASM artifact is confirmed available.

---

## Summary

`integrations/contract_client.py` has **unit test coverage via mocks** (`tests/test_contract_client.py`) but has never been exercised against a live Soroban network. The `README.md` explicitly notes:
> `--submit-onchain` assumes a deployed `ledgerlens-score` contract and a funded `LEDGERLENS_SUBMITTER_SECRET`; it has unit test coverage via mocks but hasn't been exercised against a live Soroban network from this repo.

This means the `submit_score` / `get_score` transaction construction, signing, and network submission path is **entirely untested in a real environment**. Bugs in XDR encoding, fee handling, authorisation, or contract ABI changes would only surface in production.

This issue asks you to build a complete **end-to-end integration test suite** that:
1. Deploys (or re-uses a pre-deployed) `ledgerlens-score` contract on Stellar Testnet.
2. Runs the full `--submit-onchain` pipeline path from `run_pipeline.py` against the testnet contract.
3. Reads back the submitted score via `get_score` and verifies the round-trip.
4. Runs these tests on a dedicated CI workflow (separate from the existing lint/test workflow to avoid slowing it down).

This is the most technically demanding issue in the repository. It requires deep Stellar/Soroban SDK knowledge, transaction lifecycle management, and CI infrastructure expertise.

---

## Detailed Description

### Architecture

```
CI Workflow (testnet-integration.yml)
       │
       ├── Setup: fund submitter account via Friendbot
       ├── Deploy: install + instantiate ledgerlens-score WASM
       ├── Run pipeline: python run_pipeline.py --submit-onchain (testnet)
       └── Verify: LedgerLensContractClient.get_score() → assert score stored
```

### Part 1: Testnet account and contract setup (`scripts/testnet_setup.py`)

A CLI script that:
1. **Funds the submitter account** using Horizon Testnet's Friendbot (`/friendbot?addr={public_key}`). The submitter keypair is generated from `LEDGERLENS_SUBMITTER_SECRET` or created fresh for the test run.
2. **Deploys the `ledgerlens-score` contract** by uploading the pre-compiled WASM (`ledgerlens_score.wasm`) to Testnet and invoking `create_contract`. The WASM file path is parameterised via `--wasm-path`. If a contract is already deployed (detected via `LEDGERLENS_CONTRACT_ID` env var), skip deployment.
3. **Writes** `LEDGERLENS_CONTRACT_ID` and `LEDGERLENS_SUBMITTER_SECRET` to a `.env.testnet` file so subsequent pipeline runs can pick them up.
4. Prints the deployed contract ID to stdout for CI to capture.

The pre-compiled WASM must be sourced from the `ledgerlens-contract` repository's release artifacts. Document the exact WASM version and commit hash in `tests/integration/README.md`.

### Part 2: Integration test suite (`tests/integration/`)

Create a directory `tests/integration/` with its own `conftest.py` that:
- Skips all integration tests unless `LEDGERLENS_INTEGRATION_TESTS=1` is set in the environment (so `make test` never accidentally hits the testnet).
- Loads `LEDGERLENS_CONTRACT_ID`, `LEDGERLENS_SUBMITTER_SECRET`, and `SOROBAN_RPC_URL` from environment variables (or `.env.testnet`).

**`tests/integration/test_contract_client_live.py`**:

```
test_submit_score_live               — submit a score, assert no exception raised
test_get_score_live_after_submit     — get_score returns the submitted values
test_submit_score_updates_existing   — submit twice, assert latest values are returned
test_score_benford_flag_persisted    — submit with benford_flag=True, get back True
test_confidence_field_persisted      — submit confidence=87, get back 87
test_invalid_wallet_rejected         — submit with a malformed wallet address, assert contract error
```

**`tests/integration/test_pipeline_submit_onchain.py`**:

```
test_full_pipeline_submit_onchain    — run run_pipeline.main() with --submit-onchain and
                                       a small synthetic trades DataFrame; assert at least
                                       one RiskScore is retrievable from the contract via get_score()
```

### Part 3: CI workflow (`.github/workflows/testnet-integration.yml`)

A GitHub Actions workflow that:
- Triggers on: `workflow_dispatch` (manual), and on a weekly schedule (Sundays at 03:00 UTC).
- **Does NOT run on every PR** — this is expensive and slow.
- Sets up Python 3.12, installs dependencies via `make install`.
- Generates a fresh Testnet keypair and funds it via Friendbot (or re-uses a funded keypair from GitHub Secrets).
- Runs `scripts/testnet_setup.py --wasm-path ledgerlens_score.wasm` (downloads WASM from the `ledgerlens-contract` release artifacts via `gh release download`).
- Sets `LEDGERLENS_INTEGRATION_TESTS=1` and runs `pytest tests/integration/ -v --timeout=120`.
- On success, posts a comment to the latest open PR (if any) via `gh pr comment` with the test summary.
- On failure, creates a GitHub issue with the failure log and assigns it to the repo maintainer.

### Part 4: Soroban transaction submission correctness

During implementation, verify and document:
- The exact XDR encoding of each `scval` parameter passed to `submit_score`. Confirm it matches the Soroban contract's expected parameter types by running `soroban contract invoke --id ... --fn describe_submit_score` on the deployed contract.
- Fee estimation: `ContractClient.invoke` uses simulation to estimate fees. Document the expected fee range (in XLM) per `submit_score` call on Testnet.
- Authorization: `submit_score` requires the submitter to be authorized. Document the authorization model (is the submitter baked into the contract constructor, or is it set via a separate admin call?). The setup script must handle this correctly.

---

## Requirements

### Correctness
- `get_score` must return **exactly** the values submitted by `submit_score` — no rounding, no truncation, no encoding artefacts.
- The integration tests must not be flaky: retry transient Testnet RPC failures up to 3 times with a 5-second delay before failing.
- All integration tests must complete within 120 seconds per test (enforced by `pytest-timeout`).

### Security
- `LEDGERLENS_SUBMITTER_SECRET` must be stored as a GitHub Actions secret and never logged or printed in CI output.
- The Testnet submitter account must be separate from any Mainnet or staging accounts.
- The WASM file (`ledgerlens_score.wasm`) must have its SHA-256 hash verified against the known good hash from the `ledgerlens-contract` release before deployment.

### CI isolation
- Integration tests must be **completely separate** from the main `ci.yml` workflow. `make test` must never trigger network calls.
- The `testnet-integration.yml` workflow must not block PRs — it runs on `workflow_dispatch` and a weekly schedule only.
- Any Testnet contract deployed during CI must use a deterministic salt or a CI-specific prefix so it can be identified and cleaned up.

### Documentation
- `tests/integration/README.md` — setup instructions, environment variables required, how to run locally, and the WASM version used.
- Update `CONTRIBUTING.md` to explain the separation between unit tests (`make test`) and integration tests (`LEDGERLENS_INTEGRATION_TESTS=1 pytest tests/integration/`).
- Document the Testnet fee model and expected XLM costs per pipeline run in `tests/integration/README.md`.

---

## Tests Required (mandatory — all must pass)

The integration tests listed above in Part 2 are the mandatory tests. Additionally, add unit tests for the setup script:

Add `tests/test_testnet_setup.py` (unit tests, no network):

1. **`test_setup_skips_deployment_if_contract_id_set`** — mock `LEDGERLENS_CONTRACT_ID="CA..."` in env; assert the deployment step (`ContractClient.deploy`) is **not** called.
2. **`test_setup_writes_env_file`** — mock Friendbot and deployment calls; assert `.env.testnet` is written with `LEDGERLENS_CONTRACT_ID` and `LEDGERLENS_SUBMITTER_SECRET` keys.
3. **`test_wasm_sha256_verification_rejects_bad_hash`** — provide a WASM file with an intentionally wrong content; assert a `ValueError` mentioning "SHA-256 mismatch" is raised before deployment.
4. **`test_friendbot_funding_retries_on_rate_limit`** — mock Friendbot to return 429 on the first call and 200 on the second; assert the setup script retries and succeeds.

The integration tests in `tests/integration/` are marked with `pytest.mark.integration` and are only collected when `LEDGERLENS_INTEGRATION_TESTS=1`. The CI workflow is responsible for setting this variable.

For the **unit tests**: run with `pytest tests/test_testnet_setup.py -v`

All four unit tests must pass without any network access. `make lint` and `make test` must pass with no new failures.

For the **integration tests**: run with `LEDGERLENS_INTEGRATION_TESTS=1 pytest tests/integration/ -v`

All six integration tests in `test_contract_client_live.py` plus the one in `test_pipeline_submit_onchain.py` (7 total) must pass against a live Testnet deployment.

---

## How to Apply for This Issue

**Specialty area:** Stellar/Soroban smart contract development + Python infrastructure engineering. This issue requires expertise in **both**:
- Stellar SDK (Python `stellar_sdk` library, XDR encoding, transaction lifecycle, Soroban contract invocation).
- CI/CD infrastructure (GitHub Actions, secrets management, test isolation, flakiness prevention).

When commenting to claim this issue, please include:
- Your experience with Soroban smart contract development and the Stellar Python SDK.
- Whether you have deployed Soroban contracts to Testnet before.
- Your experience designing integration test suites for blockchain applications.
- A brief description of your approach to preventing test flakiness against a live testnet RPC (2–3 sentences).
- Your GitHub handle and any relevant prior work (contract repos, Stellar developer tools, etc.).

This issue closes the final gap in the verification chain: end-to-end proof that a risk score computed by this data layer reaches the on-chain contract correctly and can be read back. It is the foundation for Mainnet deployment confidence.
