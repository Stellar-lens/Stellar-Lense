# Aggregator Error-Namespace Mapping

## Overview

`ledgerlens-aggregator` maintains its own `Error` enum (defined in
`contracts/ledgerlens-aggregator/src/lib.rs`) that is independent from the
`ledgerlens-score` contract's error namespace.  This document describes every
aggregator error variant and how it relates to the underlying shard-level score
contract errors.

## Error Variants

| Code | Variant | Description | May wrap score error |
|------|---------|-------------|---------------------|
| 1 | `AlreadyInitialized` | Aggregator has already been initialized | No |
| 2 | `NotInitialized` | Aggregator has not been initialized yet | No |
| 3 | `Unauthorized` | Caller is not the admin | No |
| 4 | `SelfReference` | Attempted to register the aggregator itself as a shard | No |
| 5 | `ShardAlreadyRegistered` | Shard address is already in the shard list | No |
| 6 | `ShardNotRegistered` | Shard address is not in the shard list (on removal) | No |
| 7 | `ShardLimitReached` | Maximum number of shards (`MAX_SHARDS`, currently 10) has been reached | No |
| 8 | `ScoreNotFound` | No shard returned a score/aggregate for the requested wallet | No |
| 9 | `NoShards` | No shards are registered (gate query cannot proceed) | No |
| 10 | `ShardFailure` | A cross-contract call to a shard failed or returned an error | **Yes** — see below |

## ShardFailure — Tracing the Root Cause

When `ShardFailure` is returned, the caller can retrieve the exact shard that
failed and the raw score-contract error code via `get_last_shard_failure`:

```rust
pub fn get_last_shard_failure(env: Env) -> Option<(Address, u32)>
```

- **`Address`** — the contract address of the shard that produced the error.
- **`u32`** — the raw error code from the `ledgerlens-score::Error` enum,
  or `0` if the shard invocation itself failed (host-level error, panic, or
  the address does not point to a valid score contract).

### Example integrator workflow

```rust
match aggregator.query_risk_gate(&wallet, &pair, &threshold) {
    Ok(true) => { /* wallet passed all shards */ }
    Ok(false) => { /* wallet rejected by at least one shard */ }
    Err(Error::ShardFailure) => {
        if let Some((shard, code)) = aggregator.get_last_shard_failure() {
            // shard is the failing contract address
            // code is the score-contract error (e.g. 2 = NotInitialized)
        }
    }
    Err(_) => { /* other aggregator error */ }
}
```

## Score Contract Error Codes (for reference)

The `ledgerlens-score::Error` enum defines the following codes that may appear
as the `u32` value inside a `ShardFailure`:

| Code | Name | Meaning |
|------|------|---------|
| 1 | `AlreadyInitialized` | Score contract already initialized |
| 2 | `NotInitialized` | Score contract not initialized |
| 3 | `Unauthorized` | Caller lacks required authorization |
| 4 | `InvalidScore` | Score value out of valid range |
| 5 | `InvalidConfidence` | Confidence value out of valid range |
| 6 | `ScoreNotFound` | No score exists for the wallet/pair |
| 7 | `ContractPaused` | Score contract is paused |
| 8 | `NoPendingAdminTransfer` | No admin transfer is pending |
| 9 | `EmptyBatch` | Batch submission is empty |
| 10 | `BatchTooLarge` | Batch exceeds maximum size |
| 11 | `ArithmeticOverflow` | Arithmetic operation overflowed |
| 12 | `UpgradeAlreadyPending` | Upgrade already pending |
| 13 | `NoPendingUpgrade` | No upgrade is pending |
| 14 | `InsufficientSigners` | Not enough signers |
| 15 | `UnauthorizedSigner` | Signer is not authorized |
| 16 | `InvalidThreshold` | Threshold value is invalid |
| 17 | `ServiceSetFull` | Service set has reached capacity |
| 18 | `SignerAlreadyInSet` | Signer already registered |
| 19 | `SignerNotInSet` | Signer not found |
| 20 | `UpgradeNotReady` | Upgrade delay has not elapsed |
| 21 | `InvalidUpgradeDelay` | Upgrade delay value is invalid |
| 22 | `InvalidStalenessWindow` | Staleness window is invalid |
| 23 | `RateLimitExceeded` | Rate limit exceeded |
| 24 | `InvalidCooldown` | Cooldown value is invalid |
| 25 | `InvalidTimestamp` | Timestamp is out of range |
| 26 | `ServicePubkeyNotSet` | Service public key not configured |
| 27 | `InvalidAttestation` | Attestation proof is invalid |
| 28 | `InvalidPubkeyLength` | Public key has invalid length |
| 29 | `InvalidHistoryDepth` | History depth is invalid |
| 30 | `InsufficientConsensus` | Insufficient consensus among models |
| 31 | `ConsensusInputEmpty` | Consensus input set is empty |
| 32 | `InvalidConsensusConfig` | Consensus configuration is invalid |
| 33 | `AdminSetFull` | Admin set has reached capacity |
| 34 | `AdminSignerNotInSet` | Admin signer not found |
| 35 | `InsufficientAdminSigners` | Not enough admin signers |
| 36 | `CyclicDelegation` | Delegation would create a cycle |
| 37 | `ScoreEmbargoed` | Wallet score is embargoed |
| 38 | `FeeTokenNotSet` | Fee token contract not set |
| 39 | `QuorumFailureWindowNotElapsed` | Quorum failure window still active |
| 40 | `RevealWindowExpired` | Commit-reveal window has expired |
| 41 | `CommitmentMismatch` | Commitment does not match reveal |
| 42 | `InvalidFinalityBuffer` | Finality buffer value is invalid |
| 43 | `NoPendingScore` | No pending score exists |
| 44 | `FinalityWindowNotElapsed` | Finality window still active |
| 45 | `InvalidDisputeBond` | Dispute bond amount is invalid |
| 46 | `DisputeAlreadyOpen` | Dispute already exists for the wallet/pair |
| 47 | `DisputeNotFound` | Dispute not found |
| 48 | `DisputeNotYetTimedOut` | Dispute timeout has not elapsed |
| 49 | `InvalidHysteresisMargin` | Hysteresis margin is invalid |
| 50 | `InvalidModelPriorWeight` | Model prior weight is invalid |

Code `0` indicates that the shard invocation itself failed at the host level
(e.g. the target address does not implement the score contract interface, or
the call panicked).

## Functions and their error behaviour

| Function | Returns | Failure behavior |
|----------|---------|-----------------|
| `initialize` | `Result<(), Error>` | `AlreadyInitialized` if called twice |
| `get_admin` | `Result<Address, Error>` | `NotInitialized` if uninitialized |
| `add_shard` | `Result<(), Error>` | `SelfReference`, `ShardAlreadyRegistered`, `ShardLimitReached` |
| `remove_shard` | `Result<(), Error>` | `ShardNotRegistered` |
| `query_risk_gate` | `Result<bool, Error>` | `NoShards` if no shards; `ShardFailure` if a shard errors (recorded via `get_last_shard_failure`) |
| `get_score` | `Result<RiskScore, Error>` | `ScoreNotFound` if no shard has data; per-shard errors stored via `get_last_shard_failure` |
| `get_aggregate_score` | `Result<AggregateRiskScore, Error>` | `ScoreNotFound` if no shard has data; per-shard errors stored via `get_last_shard_failure` |
| `get_score_across_shards` | `Vec<(Address, Option<RiskScore>)>` | Individual shard errors appear as `None` in the result vector |
| `contagion_depth_across_shards` | `u32` | Silently skips erring shards; per-shard errors stored via `get_last_shard_failure` |
