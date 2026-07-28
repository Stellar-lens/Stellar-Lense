# On-Chain Governance

LedgerLens uses a lightweight on-chain governance module for admin parameter
changes and contract WASM upgrades. Both flows follow the same high-level
pattern:

```
propose → time-lock → execute (or veto)
```

This document covers **parameter change governance**. For WASM upgrade
governance, see the [Upgrade Governance](../README.md#upgrade-governance)
section in the README.

## Motivation

Admin functions such as `set_cooldown`, `set_decay_rate`,
`set_score_velocity_cap`, and `set_history_max_depth` previously took effect
immediately when called by the admin multi-sig. A compromised admin key could
alter core contract parameters without giving the community or service signers
time to react.

Parameter change governance introduces a mandatory delay between proposal and
execution, with a service-signer veto window during the first half of that
delay.

## Flow

```
 Admin                          Contract                         Service signers
   │                               │                                    │
   │ propose_parameter_change      │                                    │
   ├──────────────────────────────►│  store ParameterProposal           │
   │                               │  emit prm_prop                     │
   │                               │                                    │
   │         [0 .. time_lock/2]    │  veto window open                  │
   │                               │◄───────────────────────────────────┤
   │                               │  veto_parameter_change (optional)  │
   │                               │                                    │
   │         [time_lock/2 .. lock] │  irrevocable until execute/expiry  │
   │                               │                                    │
   │ execute_parameter_change      │                                    │
   ├──────────────────────────────►│  apply param, mark Executed        │
   │                               │  emit prm_exec                     │
```

### 1. Propose

An admin calls `propose_parameter_change(admin_signers, param_key, new_value)`.

- Validates the parameter key and value (same bounds as the direct setter).
- Records a `ParameterProposal` with `time_lock_secs = get_upgrade_delay()`
  (minimum 48 hours / `MIN_UPGRADE_DELAY_SECS`).
- Returns a monotonic `proposal_id`.
- Emits `prm_prop`.
- At most **10** proposals may be pending at once.

### 2. Veto (service signers)

During the first half of the time-lock (`now <= proposed_at + time_lock_secs / 2`),
service signers may call `veto_parameter_change(service_signers, proposal_id)`.

- Uses the same M-of-N service signer authorization as score submission.
- Marks the proposal `Vetoed` and removes it from the pending index.
- Emits `prm_veto`.
- After the veto deadline the proposal is **irrevocable** until execution or
  expiry.

### 3. Execute (admin)

After the full time-lock elapses (`now >= proposed_at + time_lock_secs`), an
admin calls `execute_parameter_change(admin_signers, proposal_id)`.

- Re-checks the ledger timestamp at execution time (never cached).
- Applies the parameter change via the same storage paths as the direct setters.
- Marks the proposal `Executed` so it cannot be applied again.
- Emits `prm_exec`.

### 4. Expiry

If a proposal is neither executed nor vetoed within `time_lock_secs * 2`, it
expires and can no longer be executed. Attempting execution marks it `Expired`
and returns `ParameterProposalExpired`.

## Supported Parameters

| `param_key` symbol | Direct setter | `new_value` encoding |
|--------------------|---------------|----------------------|
| `cooldown` | `set_cooldown` | 8-byte big-endian `u64` (seconds) |
| `hist_dep` | `set_history_max_depth` | 4-byte big-endian `u32` |
| `decay_rt` | `set_decay_rate` | 8 bytes: numerator `u32` BE + denominator `u32` BE |
| `vel_cap` | `set_score_velocity_cap` | 1 byte enabled (`0`/`1`) + 4-byte `u32` points/hour |
| `upg_dlay` | `set_upgrade_delay` | 8-byte big-endian `u64` (seconds) |

## Read APIs

- `get_parameter_proposal(proposal_id)` — returns the full
  `ParameterProposalRecord` (proposal + status). Callable by anyone.
- `get_pending_param_prop_ids()` — returns IDs still marked pending.

## Security Properties

| Threat | Mitigation |
|--------|------------|
| Instant parameter change by compromised admin | No instant path — every change waits out the full time-lock |
| Service signers blocked from reacting | Veto window during first half of time-lock |
| Stale execution after community objection period | Veto deadline at `time_lock_secs / 2`; irrevocable after |
| Replay / double execution | Executed proposals marked in storage |
| Unbounded storage growth | Cap of 10 concurrent pending proposals; expiry at `2 × time_lock` |
| Time-lock too short | Minimum `MIN_UPGRADE_DELAY_SECS` (48 hours), shared with upgrade governance |

## Events

| Topic | When |
|-------|------|
| `prm_prop` | Proposal created `(proposal_id, param_key, executable_after)` |
| `prm_exec` | Parameter applied `(proposal_id, param_key)` |
| `prm_veto` | Proposal vetoed `(proposal_id, vetoer)` |
| `prm_clean` | Expired proposals cleaned up `(count, oldest_kept_timestamp)` |

## Proposal Cleanup and Lifecycle

Proposals expire at `proposed_at + time_lock_secs * 2` and can no longer be executed. To reclaim storage and
prevent unbounded growth:

1. Call `get_parameter_proposal(proposal_id)` to check status — once `Expired`, ready for cleanup.
2. Call `cleanup_expired_parameter_proposals(admin_signers)` to permanently remove expired proposals
   that have been expired for **at least 48 hours**.
3. Emits `prm_clean` event with count and oldest retained proposal timestamp.
4. Idempotent — safe to call repeatedly without side effects.

## Governance Simulation and Audit

Before proposing or executing a parameter change, preview its effects without applying it:

1. **Pre-proposal validation**: Call `simulate_parameter_change(param_key, new_value)` to preview the change
   before creating a proposal. Returns before/after values, affected subsystems, and execution window.
2. **Proposal audit**: Call `get_proposal_simulation(proposal_id)` to review the simulated impact of an
   existing proposal during the time-lock window. Deterministic output for reproducible audit trails.
3. **Simulation output includes**:
   - `param_key` — which parameter is changing
   - `current_value` — serialized current parameter value
   - `new_value` — proposed new value
   - `affected_capabilities` — list of subsystems affected (e.g., `["decay", "score"]` for decay rate)
   - `execution_window_start` — earliest execution timestamp
   - `execution_window_end` — expiry timestamp (execution stops being possible after this)

## Two-Person Control for Destructive Operations

Irreversible operations such as `bulk_reset_pair_weight` (clears all pair-weight assignments)
can be gated to require multi-admin approval:

1. Admin calls `set_require_multisig_for_destructive(admin_signers, true)` to **enable** the policy.
2. When policy is **enabled**:
   - `bulk_reset_pair_weight` rejects if supplied with only 1 admin signer.
   - Returns `InsufficientAdminSigners` error.
   - Requires at least **2** admin signers in the call.
3. When policy is **disabled** (default):
   - `bulk_reset_pair_weight` works as before — single admin sufficient.
4. Policy defaults to **disabled** for backward compatibility.
5. Admin can toggle on/off at any time with `set_require_multisig_for_destructive`.

## Emergency Pause Decision Trees

### Global Contract Pause (Circuit Breaker)

**Scenario**: Compromised service signer, malicious score submissions, or critical vulnerability.

```
├─ Call: pause(admin_signers)
│  │
│  ├─ Effect: All score submissions blocked immediately
│  ├─ Read behavior: get_score() still works (returns stale scores)
│  └─ Time to recover: Admin unpause or automatic unpause after TTL (~1 hour)
│
└─ Recovery:
   └─ When safe, call: unpause(admin_signers)
      └─ Effect: Submissions resume; no data loss
```

**When to use**: System-wide threat or malicious activity. Affects all asset pairs and wallets.

### Per-Pair Pause (Granular Circuit Breaker)

**Scenario**: Single asset pair experiencing anomalies, oracle failure, or market disruption.

```
├─ Call: set_pair_paused(admin_signers, asset_pair, true)
│  │
│  ├─ Effect: Submissions for ONLY this pair blocked
│  ├─ Read behavior: get_score(wallet, asset_pair) returns stale score; other pairs unaffected
│  └─ Time to recover: Immediate manual unpause
│
└─ Recovery:
   └─ When pair is stable, call: set_pair_paused(admin_signers, asset_pair, false)
      └─ Effect: Pair submissions resume
```

**When to use**: Isolated pair problem (e.g., oracle delay, price spike, model miscalibration).
Minimal blast radius; other pairs continue operating normally.

### Submission Freeze (Submit Path Only)

**Scenario**: Need to pause submissions while keeping reads active (e.g., during emergency upgrade).

```
├─ Call: set_submission_freeze(admin_signers, true)
│  │
│  ├─ Effect: submit_scores() and related write operations blocked
│  ├─ Read behavior: get_score(), query_risk_gate() work normally with stale data
│  └─ Time to recover: Immediate manual unfreeze or automatic after TTL
│
└─ Recovery:
   └─ When ready, call: set_submission_freeze(admin_signers, false)
      └─ Effect: Submissions resume
```

**When to use**: Maintenance, data migration, or temporary service disruption. Readers (consuming protocols)
stay unaffected; dApps querying LedgerLens can continue operating during the freeze.

### Decision Matrix

| Scenario | Action | Reversibility | Impact | TTL |
|----------|--------|---------------|---------|----|
| All submissions compromised | `pause(true)` | Manual unpause | Complete halt | ~1 hour |
| Single pair malfunction | `set_pair_paused(pair, true)` | Manual unpause | Pair-only halt | None (manual) |
| Need read-only mode | `set_submission_freeze(true)` | Manual unfreeze | Write-only halt | ~1 hour |
| Score data loss risk | Upgrade + redeploy | Redeploy | Full reset | Manual |

## Maintenance and Administration

### Regular Maintenance Tasks

1. **Weekly**: Review `get_pending_param_prop_ids()` for stalled proposals; veto or wait for expiry.
2. **Monthly**: Run `cleanup_expired_parameter_proposals(admin_signers)` to reclaim storage.
3. **Before upgrades**: Simulate parameter changes with `simulate_parameter_change` to preview impact.
4. **Incident response**: Check pause status with `is_paused()` and `is_pair_paused(pair)`.

### Audit Trail

- All governance actions emit events: `prm_prop`, `prm_exec`, `prm_veto`, `prm_clean`.
- Integrate with off-chain logging to build a tamper-evident proposal history.
- Use `simulated_at` timestamp in `get_proposal_simulation()` output to track audit window.

## Related

- WASM upgrade governance: `propose_upgrade` / `execute_upgrade` / `veto_upgrade`
- Upgrade delay configuration: `set_upgrade_delay` / `get_upgrade_delay`
- Threat model: [`SECURITY.md`](../SECURITY.md#upgrade-governance--threat-model)
