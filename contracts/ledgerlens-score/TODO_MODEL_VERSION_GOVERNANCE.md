# TODO: Model Version Governance + Deprecated version rejection

## Step 1 — Add types
- [ ] Update `src/types.rs`:
  - Add `ModelVersionStatus` enum (Proposed/Active/Deprecated)
  - Add storage key variants under `DataKey` for per-version registry (status, proposed executable timestamp, description)

## Step 2 — Add errors + events
- [ ] Update `src/errors.rs`:
  - Add `ModelVersionDeprecated`
  - (If needed) add `ModelVersionNotReady` / `ModelVersionAlreadyProposed` / `ModelVersionNotProposed` / `ModelVersionNotActive` equivalents.
- [ ] Update `src/events.rs`:
  - Add `model_version_proposed`
  - Add `model_version_activated`
  - Add `model_version_deprecated`

## Step 3 — Add storage helpers
- [ ] Update `src/storage.rs`:
  - Add getters/setters for per-version status and proposed executable_after timestamp
  - Add helper `get_model_version_status(version)`

## Step 4 — Contract methods
- [ ] Update `src/lib.rs` to expose admin methods:
  - `propose_model_version(admin_signers, version, description)`
  - `approve_model_version(admin_signers, version)`
  - `deprecate_model_version(admin_signers, version)`
  - `get_model_version_status(version)`
- [ ] Enforce admin auth via existing `require_admin_auth` helper.
- [ ] Enforce timelock semantics:
  - `approve_model_version` must fail if `now < proposed_at + upgrade_delay`.

## Step 5 — Submission gating
- [ ] Update `submit_score`:
  - Reject if `model_version` is `Deprecated` with `Error::ModelVersionDeprecated`.
- [ ] Update `submit_scores_batch` and `submit_scores_batch_attested`:
  - For each entry, set `rejection_code = Error::ModelVersionDeprecated as u32` when deprecated.

## Step 6 — Tests
- [ ] Update `src/test.rs`:
  - Lifecycle timelock test: propose → too-early approve fails → after delay approve succeeds → deprecate succeeds.
  - Submission rejection test: submitting with deprecated model version fails.
  - Batch rejection: deprecated version entry rejected with correct `rejection_code`.

## Step 7 — Build & test
- [ ] Run `cargo test -p ledgerlens-score`.

