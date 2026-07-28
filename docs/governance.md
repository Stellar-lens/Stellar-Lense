# On-Chain Governance

LedgerLens uses a lightweight on-chain governance module for admin parameter
changes and contract WASM upgrades. Both flows follow the same high-level
pattern:

```
propose → time-lock → execute (or veto)
```

This document covers **parameter change governance** and the **governance action
registry**.  For WASM upgrade governance, see the
[Upgrade Governance](../README.md#upgrade-governance) section in the README.

## Governance Action Registry

Every privileged admin action is assigned a **stable `u8` discriminant** in
`contracts/ledgerlens-score/src/governance_actions.rs`.  This registry is the
single source of truth for action identifiers — no other file may introduce a
new raw byte literal for a governance action.

### Why a registry?

Before the registry, each audit-chain entry was stamped with an ad-hoc magic
byte (e.g. `0x01`, `0x02`) defined inline with only a terse comment.  There
was no central lookup, no uniqueness guarantee, and no stable name exposed to
events or documentation.  The registry fixes all three:

| Problem | Solution |
|---------|----------|
| Magic bytes scattered in `lib.rs` | All discriminants live in one module with doc-comments |
| No compile-time uniqueness check | Each constant has a distinct value; `is_known_action()` can detect gaps |
| Events carried no action type | `gov_action` event embeds `action_id` and `action_name` |
| Off-chain tools had to decode raw bytes | `all_actions()` provides a stable reverse-lookup slice |

### Stability rules

1. **Discriminants are frozen once assigned.**  Off-chain audit-chain replay
   tools reconstruct the Merkle root by replaying stored discriminants.  A
   reassignment silently corrupts every root that followed the change.
2. **New actions claim the next sequential value.**  Predictable ordering makes
   manual inspection and test fixtures easier.
3. **`0x00` is reserved** (uninitialized / zeroed payload sentinel).
4. **Name strings must be ≤ 9 ASCII characters** so they fit in a Soroban
   `symbol_short!()`.

### Registry table

| Discriminant | Constant | Name (`action_name()`) | Contract function |
|:------------:|----------|------------------------|-------------------|
| `0x00` | `GOV_ACTION_RESERVED` | *(reserved)* | — |
| `0x01` | `GOV_ACTION_SET_SERVICE` | `set_svc` | `set_service` |
| `0x02` | `GOV_ACTION_ADD_SERVICE_SIGNER` | `add_sig` | `add_service_signer` |
| `0x03` | `GOV_ACTION_SET_ADMIN_THRESHOLD` | `set_athr` | `set_admin_threshold` |
| `0x04` | `GOV_ACTION_PAUSE` | `pause` | `pause` |
| `0x05` | `GOV_ACTION_UNPAUSE` | `unpause` | `unpause` |
| `0x06` | `GOV_ACTION_PROPOSE_UPGRADE` | `upg_prop` | `propose_upgrade` |

### `gov_action` event

Every time a governance action is appended to the Merkle audit chain the
contract emits a `gov_action` event:

```
Topic:  ("gov_action", EVENT_VERSION)
Data:   (action_id: u32, action_name: Symbol, new_head: BytesN<32>)
```

`action_id` is the discriminant from the table above.  `action_name` is its
human-readable name string.  `new_head` is the updated Merkle root after the
action was folded in.  Off-chain indexers can filter by `action_id` to build a
typed timeline of all admin activity without decoding raw chain bytes.

### Adding a new action

1. Append a new `GOV_ACTION_*` constant in `governance_actions.rs` using the
   next available discriminant.
2. Add a matching `GOV_ACTION_NAME_*` string constant (≤ 9 chars).
3. Add an arm to `action_name()` and an entry to `all_actions()`.
4. Update this table.
5. Call `Self::append_governance_action(&env, GOV_ACTION_YOUR_ACTION, &data)`
   at the relevant call site in `lib.rs` — **never** call
   `append_governance_action_raw` directly for new actions.

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

## Related

- WASM upgrade governance: `propose_upgrade` / `execute_upgrade` / `veto_upgrade`
- Upgrade delay configuration: `set_upgrade_delay` / `get_upgrade_delay`
- Threat model: [`SECURITY.md`](../SECURITY.md#upgrade-governance--threat-model)
