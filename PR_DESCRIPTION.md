# PR: Production Launch and Ongoing Operations Readiness Review

> **Issue:** #635
> **Branch:** fix/issue-635-production-launch-readiness
> **Type:** Production readiness, operations tooling, documentation

---

## Design Section: Trust Assumptions, Authorization Boundaries, State Transitions, Failure Modes, and Rollback/Recovery

### Trust Assumptions

1. **Stellar network honesty:** Contract execution is deterministic and correctly ordered by Stellar consensus. Ledger timestamps are trusted for time-bound governance (finality buffer, upgrade delay, model version timelocks).
2. **Admin key security:** The admin key or multi-sig is stored in a hardware wallet or HSM accessible only to authorised operators. Compromise of the admin key is the primary threat model.
3. **Service key security:** The off-chain service account's secret key is stored securely and used only by the authorised detection pipeline.
4. **Signing key compromise mitigation:** If the service signing key (`set_service_pubkey`) is compromised, the admin can rotate the key via `set_service_pubkey` or `rotate_service_pubkey` and invalidate the old nonce.
5. **Deterministic execution:** Soroban contract execution is deterministic across all nodes. No Byzantine behaviour from the Stellar network itself.
6. **Wasm binary integrity:** The WASM built from the audited source code is the binary deployed to mainnet. Reproducible build verification provides this guarantee.

### Authorization Boundaries

| Role | Capabilities | Boundary |
|------|-------------|----------|
| Admin | All governance ops, pause/unpause, pair pausing, service rotation, upgrade proposals | Time-locked changes; multi-sig recommended |
| Service (legacy) | Direct `submit_score` calls | Single key; compromised = all scores forged |
| Service Set (multi-sig) | `submit_score` via signer auth | M-of-N threshold; compromised signers removable |
| Anyone | Read-only queries (`get_score`, `get_admin`, etc.) | No state modification |

### State Transitions

```
Contract Lifecycle:
  Uninitialized → Initialized → Active ↔ Paused

Score Submission Lifecycle:
  Direct (buffer=0) → Committed immediately
  Buffered (buffer>0) → Pending → Committed (after buffer elapsed)

Upgrade Lifecycle:
  No proposal → Proposed → (48h delay) → Executed
  Proposed → Vetoed (within first half of delay)
  Proposed → Expired (2× delay elapses)

Parameter Change Lifecycle:
  No proposal → Proposed → (time-lock) → Executed
  Proposed → Vetoed (within first half)
  Proposed → Expired (2× time-lock)

Model Version Lifecycle:
  Proposed → (upgrade_delay) → Active → Deprecated (permanent)
```

### Failure Modes and Mitigations

| Failure Mode | Impact | Mitigation | Recovery |
|-------------|--------|------------|----------|
| Admin key compromise | Unrestricted parameter/schedule changes | Time-locked changes, multi-sig, audit trail | Rotate admin key via `transfer_admin` |
| Service key compromise | Forged score submissions | Key rotation, per-signature nonce | Rotate service key, invalidate nonce |
| Finality buffer stuck | Scores pending forever | Admin cancellation via `cancel_pending_score` | Cancel stuck pending scores |
| Stale data | Scores don't reflect current risk | TTL-based archival + rental sweep | Run `extend_entry_ttls`, re-submit |
| Partial batch execution | Some entries fail, others succeed | Per-entry rejection codes in `BatchResult` | Review codes, fix and re-submit |
| Signer loss (service set) | Threshold can't be met | `set_service_threshold` can lower threshold | Replace lost signers |
| Unavailable off-chain pipeline | No new scores submitted | Contract doesn't depend on pipeline availability | Restore pipeline, re-submit |
| Interrupted retry / duplicate | Rejected by cooldown | Cooldown prevents rapid re-submission | Wait for cooldown, re-submit |
| Replay attack | Old score replayed | Timestamp validation, nonce-based attestation, commitment binding | Prevented by design |
| WASM upgrade failure | Broken contract logic | Time-locked upgrade with veto window | Re-propose previous WASM |
| Stale epoch | Submissions rejected | Admin can open/close epochs | Admin opens new epoch |

### Rollback and Recovery

#### Code Rollback (WASM)
1. Obtain previous WASM binary from version control.
2. Compute SHA-256 hash.
3. `propose_upgrade` with previous hash.
4. Wait for upgrade delay (default 48 hours) to elapse.
5. `execute_upgrade` to install previous WASM.
6. Verify with `get_version` and smoke tests.

#### Parameter Rollback
- If still in veto window: `veto_parameter_change`.
- If past veto window: wait for expiry or propose inverse change.
- If already executed: propose original value as new change.

#### Data Rollback
- On-chain state cannot be automatically rolled back.
- Use `clear_score` / `clear_score_history` (admin-only, irreversible) for targeted removal.
- Recommended for data corruption: deploy new contract, migrate authorised integrators.

#### Data Recovery
1. Deploy fresh contract instance.
2. Initialize with backed-up admin and service addresses.
3. Reconfigure all parameters.
4. Re-add service signers and set threshold.
5. Re-submit historical scores from off-chain pipeline data store.
6. Update all integrators with new contract ID.

---

## Production Implementation Changes

### 1. Production Readiness Runbook (`docs/production-readiness.md`)
- Defines 16 measurable readiness criteria (R1–R16) with owners, alert thresholds, and evidence requirements.
- Documents trust assumptions, authorization boundaries, state transitions, failure modes, and rollback/recovery procedures.
- Includes monitoring signal map, pre-production activation checklist, post-deployment verification checklist, and emergency response procedures.
- Covers CPU, memory, ledger reads/writes, event bytes, and encoded input size resource bounds.
- Lists alternatives considered and the invariant each design choice protects.

### 2. Operations Runbook (`docs/ops-runbook.md`)
- Detailed step-by-step procedures for routine operations: deploy, rotate service key, extend entry TTLs, monitor contract health.
- Failure scenario diagnostic and recovery procedures for 8 distinct failure modes (global pause, per-pair freeze, service key compromise, stale data, upgrade failure, stuck pending scores, signer rotation failure, unavailable dependencies, interrupted retry).
- Backup and restore procedures with configuration export/import.
- Diagnostic command reference for full contract state dumps.
- Monitoring dashboard query reference.

### 3. Canary Deployment Script (`scripts/canary-deploy.sh`)
- Builds release WASM with locked dependencies.
- Optimizes WASM binary.
- Deploy to testnet/futurenet as a canary.
- Initializes and runs smoke test score submission.
- Verifies canary state (admin, service, version, paused status).
- Logs all actions with timestamps for audit trail.
- Saves canary contract ID for post-deployment reference.

### 4. Emergency Rollback Script (`scripts/rollback.sh`)
- Proposes previous WASM as a rollback upgrade.
- Guides operator through the time-lock delay.
- Executes rollback upgrade after delay elapses.
- Verifies rollback success (version, admin, smoke tests).
- Mainnet safety guard requiring explicit confirmation.

### 5. Post-Deployment Verification Script (`scripts/verify-deployment.sh`)
- Checks basic contract state (admin, service, version, pause status).
- Runs functional smoke test (submit score, retrieve score).
- Checks pending upgrade status.
- Verifies service set configuration.
- Produces pass/fail/warn summary suitable for audit records.

### 6. Failure Injection Script (`scripts/failure-injection.sh`)
- Supports 7 adversarial scenarios:
  - `partial-signer-loss` — reduces threshold, verifies rejection, restores
  - `stale-data` — closes epoch, verifies rejection, opens new epoch
  - `replay-attack` — attempts duplicate submission, verifies cooldown rejection
  - `zero-value` — submits score=0 (valid) and timestamp=0 (invalid)
  - `max-value` — submits score=101 and confidence=101 (both invalid)
  - `unauthorized-caller` — attempts operations without proper auth
  - `interrupted-retry` — submits, fails, retries within cooldown
- Each scenario diagnoses and recovers from the failure condition.

### 7. Enhanced Replay Tool (`tools/replay/`)
- Added failure injection mode to `replay/src/main.rs` with support for NDJSON failure scenario files.
- Added `process_failure_scenario()` function to process adversarial input files.
- Added `run_failure_injection()` function covering all 7 scenario types.
- Enhanced integration tests with 12 adversarial test cases:
  - `test_adversarial_unauthorized_caller_rejected`
  - `test_adversarial_zero_score_accepted` (boundary)
  - `test_adversarial_max_score_accepted` (boundary)
  - `test_adversarial_score_101_rejected` (maximum-plus-one)
  - `test_adversarial_timestamp_zero_rejected` (zero value)
  - `test_adversarial_repeated_submission_rate_limited` (replay/duplicate)
  - `test_adversarial_batch_too_large_rejected` (bounded collection)
  - `test_adversarial_empty_batch_rejected`
  - `test_adversarial_paused_pair_rejected` (pair pause)
  - `test_adversarial_globally_paused_rejected` (global pause)
  - `test_adversarial_replay_same_wallet_pair_cooldown` (rate limit / replay)
  - `test_adversarial_stale_timestamp_rejected` (stale state)
  - `test_adversarial_max_batch_exactly_at_limit` (boundary)
- Enhanced integration test coverage with deterministic replay and rate-limiting scenarios.

### 8. Deploy Script Enhancement (`deploy.sh`)
- Existing deploy script already supports dry-run mode and mainnet guard.
- Canary deployment mode enabled via `scripts/canary-deploy.sh`.
- Post-deployment verification via `scripts/verify-deployment.sh`.

---

## Alternatives Rejected and Invariants Protected

| Alternative | Rejected Because | Invariant Protected |
|-------------|------------------|---------------------|
| No canary deployment | Production failures with no prior warning | Safety — gradual rollout catches issues before full exposure |
| No rollback tooling | Operators would manually reverse upgrades without guidance | Recovery — deterministic rollback reduces operator error |
| No failure injection | Resilience cannot be verified without adversarial testing | Resilience — the contract handles partial failures gracefully |
| No post-deployment verification | Incomplete deployments could go unnoticed | Correctness — every deployment is verified end-to-end |
| No production readiness checklist | Readiness is subjective and unmeasurable | Determinism — measurable criteria ensure consistent evaluation |
| Unlimited batch size | Unbounded CPU/memory/ledger ops per transaction | Boundedness — resource consumption is predictable |
| Immediate admin changes (no time-lock) | Allows instant manipulation by compromised admin | Authorization — no unauthorized parameter mutation without reaction time |
| No finality buffer | Scores committed immediately with no review window | Safety — admin can catch and cancel erroneous submissions |
| No pause mechanism | Cannot halt contracts in emergency | Safety — the ability to stop all score submission activity |
| Per-entry attestation in batch | Prohibitively expensive in Soroban fees | Efficiency — batch attestation provides cryptographic integrity at lower cost |
| No replay tooling | Cannot verify deterministic behavior with real data | Verification — reproducible testing with real data |
| No operational runbook | Operators lack documented procedures for failure scenarios | Operability — documented procedures reduce MTTR |

---

## Resource Bounding Evidence

### CPU (worst case)
- `submit_score`: O(1) main path + O(S) service signer validation (S ≤ `MAX_SERVICE_SIGNERS` = 32).
- `submit_scores_batch`: O(N) where N = batch size (N ≤ `MAX_BATCH_SIZE` = 100).
- All loops iterate over bounded collections with known maximum sizes.

### Memory
- All Soroban collections (`Vec`, `Map`) release memory when out of scope at end of invocation.
- `BatchResult.results` is bounded by `MAX_BATCH_SIZE` = 100.
- No persistent allocations grow without bound.

### Ledger Reads/Writes
- `submit_score`: 1 write (live score) + 1 write (history) + O(1) reads for configuration.
- `submit_scores_batch`: N writes + N history pushes + N reads per batch entry (N ≤ 100).
- All reads are direct key lookups (O(1)); no full-table scans.

### Event Bytes
- Each event is a fixed-size or small-variable-length Struct.
- `score_submitted` event ≈ 150 bytes.
- Batch events emitted once per batch, not per entry.

### Encoded Input Size
- `submit_score` input: bounded by fixed-size parameters + optional attestation (max ~133 bytes for secp256k1 signature + nonce).
- `submit_scores_batch` input: bounded by `MAX_BATCH_SIZE` × `ScoreSubmission` (≈ 60 bytes each) ≈ 6 KB maximum.
- All `BytesN<32>` and `BytesN<64>` inputs are fixed size.

---

## Checklists

### Entry Points Affected
- `submit_score` — unchanged signature, enhanced error handling
- `submit_scores_batch` — unchanged signature, enhanced batch processing
- `pause` / `unpause` — unchanged, now documented in runbook
- `set_pair_paused` — unchanged, now documented in runbook
- `propose_upgrade` / `execute_upgrade` / `veto_upgrade` — unchanged, now documented in runbook
- `set_service` / `rotate_service_pubkey` — unchanged, now documented in runbook

### Storage Keys Affected
- No new storage keys added by this PR; existing keys documented in `docs/storage-layout.md`
- `DataKeyC::AdminAuditRoot` — unchanged
- `PendingScoreEntry` entries — unchanged
- `UpgradeProposal` storage — unchanged

### Events Emitted
- All existing events unchanged; no new events introduced
- `contract_paused`, `contract_unpaused` — now documented in runbook
- `score_pending`, `score_committed`, `score_pending_cancelled` — now documented in runbook
- `upgrade_proposed`, `upgrade_executed` — now documented in runbook

### Errors Used
- All existing error discriminants unchanged and compatible
- `ContractPaused`, `RateLimitExceeded`, `InvalidScore`, `InvalidTimestamp` — now documented with adversarial test coverage

### Tests Affected/Added
- `tools/replay/tests/integration_test.rs` — 12 new adversarial test cases
- `tools/replay/src/main.rs` — failure injection mode
- Existing test suite unchanged and passing

---

## Repository Compatibility Checks

All of the following checks must pass before this PR is considered production-ready:

1. `cargo fmt --all -- --check` — formatting
2. `cargo clippy --all-targets -- -D warnings` — strict clippy
3. `cargo test --workspace` — all native workspace tests
4. `cargo build --target wasm32-unknown-unknown --release -p ledgerlens-score --locked` — locked release WASM build
5. `cargo +1.88.0 audit --ignore RUSTSEC-2026-0009` — security audit
6. `tools/check_error_discriminants.sh` — error discriminant stability
7. Reproducible build verification (two independent builds produce identical WASM)
8. WASM size within budget (`scripts/wasm-size-report.sh`)

---

closes #635

---

## Issues #709, #710, #711 — Storage Invariants, Migration Rollback Fixtures, Shard Capability Attestation

### Summary

This change implements three storage-hardening issues:

| Issue | Title | Files Changed |
|-------|-------|---------------|
| #710 | Executable storage invariants | `invariants.rs`, `test_invariants.rs`, `lib.rs` |
| #709 | Migration rollback fixtures | `test_migration_rollback.rs`, `lib.rs` |
| #711 | Shard capability attestation | `aggregator/lib.rs`, `aggregator/test.rs` |

### ABI Compatibility

**ledgerlens-score:** No new public methods. `invariants.rs` helpers are `#[cfg(any(test, feature = "testutils"))]` only — zero WASM footprint impact in production builds.

**ledgerlens-aggregator:** Two new read-only methods added:
- `get_shard_capabilities(shard: Address) → Vec<Symbol>` — returns snapshot stored at `add_shard` time.
- `shard_capabilities_downgraded(shard: Address) → bool` — live capability check against snapshot.

Both are purely additive and do not change the behaviour of any existing method.

### Event Compatibility

No new events emitted. Existing event schemas unchanged.

### Storage Compatibility

- **`ShardCapabilities(Address)`** — new instance-storage key in the aggregator. Written on `add_shard`, removed on `remove_shard`. Shards registered before deployment have no snapshot; `get_shard_capabilities` returns an empty `Vec` for those.
- All score-contract storage schemas are unchanged.

### Resource Usage

- `invariant_check` is gated to `#[cfg(test)]` — zero production overhead.
- `probe_capabilities` in `add_shard` adds N cross-contract reads (one per candidate capability, bounded by the `all_caps` array length of 8). This is a one-time cost at registration time, not on the hot path.
- Migration fixture tests use `env.budget().reset_unlimited()` for the worst-case index capacity test only; all other tests run within default budgets.

### Rollback/Recovery

- The new `ShardCapabilities` key is benign to leave behind if a rollback is necessary: it is read-only and skipped when the shard is not in the `Shards` list.
- The invariant functions are test-only and have no state impact on production.
