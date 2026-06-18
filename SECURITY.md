# Security Policy

## Scope

This policy covers the **`ledgerlens-score` Soroban smart contract** and the surrounding deployment tooling in this repository.

Out-of-scope:
- The off-chain detection pipeline (`core`, `data` repos)
- The public API server (`api` repo)
- The web dashboard (`dashboard` repo)

## Supported Versions

| Contract version | Status  |
|-----------------|---------|
| 1.x (testnet)   | Active  |
| 0.x (pre-release)| Not supported |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report security issues by emailing **security@ledgerlens.io** with the subject line:

```
[SECURITY] <short description>
```

Include:

1. A clear description of the vulnerability and the affected contract function(s).
2. Steps to reproduce or a proof-of-concept (PoC) — even a pseudocode sketch helps.
3. The potential impact (e.g. unauthorized score submission, admin key extraction, fund loss if integrated with an AMM).
4. Your contact details if you would like to be credited.

## Response Timeline

| Milestone                     | Target            |
|------------------------------|-------------------|
| Acknowledgement              | Within 48 hours   |
| Triage and severity rating   | Within 7 days     |
| Fix or mitigation in testnet | Within 21 days    |
| Public disclosure            | After fix ships   |

We follow [Responsible Disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure). We will not take legal action against researchers who follow this policy.

## Contract Threat Model

| Attack vector                        | Mitigation                                                        |
|--------------------------------------|-------------------------------------------------------------------|
| Unauthorized score write             | `submit_score` requires `service.require_auth()`                  |
| Compromised service key              | `pause()` halts submissions; `set_service()` rotates the key      |
| Accidental admin key loss            | Two-step transfer: new admin must call `accept_admin()`           |
| Score poisoning via out-of-range data | `score` and `confidence` clamped to 0-100 on-chain               |
| DoS via unbounded storage            | History ring buffer capped at `HISTORY_MAX_DEPTH` (10) per pair  |
| Large batch denial of service        | Batch size capped at `MAX_BATCH_SIZE` (20) per invocation        |
| Compromised service floods a pair with submissions | Per-`(wallet, asset_pair)` cooldown (`RateLimitExceeded`); admin-bounded `[MIN_COOLDOWN_SECS, MAX_COOLDOWN_SECS]`, with `override_rate_limit` as an audited emergency escape hatch |
| Silent malicious contract upgrade    | Time-locked upgrade governance (see below): mandatory delay + on-chain proposal anyone can inspect, plus admin veto |
| Data-residency / GDPR erasure request | `clear_score_history` and `clear_score` (admin-only) permanently remove scoring data from persistent storage; `clr_hist` / `clr_scr` events provide an on-chain audit trail of every erasure |

## Upgrade Governance & Threat Model

Soroban contracts are immutable once deployed, but the admin can replace the
entire WASM via `env.deployer().update_current_contract_wasm(...)`. Left
ungoverned, a single admin key (or a compromised one) could swap in a backdoor
— disabling auth checks, redirecting score writes, or bricking integrations —
in **one transaction, with no warning**. To remove that single point of
instant failure, upgrades are gated behind an on-chain time-lock.

### The flow

1. **Propose** — the admin calls `propose_upgrade(new_wasm_hash)`. This stores
   an `UpgradeProposal` (committed hash, `proposed_at`, `executable_after`,
   `proposed_by`) and emits `upgrade_proposed`. It does **not** change the code.
2. **Monitoring window** — for at least `MIN_UPGRADE_DELAY_SECS` (48 hours;
   configurable up to 14 days) nothing can execute. Anyone — users, monitoring
   bots, integrating protocols — can call `get_pending_upgrade` to read the
   committed hash and `executable_after`, diff the proposed WASM, and alert the
   community.
3. **Execute or veto** — only after `executable_after` can the admin call
   `execute_upgrade`, which re-checks the clock at execution time (never a
   cached decision) before installing the WASM. At any point during the window
   the admin can `veto_upgrade` to cancel — the escape hatch if a proposal is
   malicious or the key was compromised. The veto emits `upgrade_vetoed` naming
   the caller, completing the audit trail.

### Threat model

| Concern | Mitigation |
|---------|------------|
| Admin pushes a backdoor instantly | No instant path exists — every upgrade waits out the full delay before `execute_upgrade` will run |
| Compromised **service** key triggers an upgrade | Service keys have no upgrade powers; only the current admin can propose/execute/veto |
| Caller manipulates the time-lock | Deadlines derive from `env.ledger().timestamp()`, which is deterministic and not caller-settable |
| Stale/early execution | `execute_upgrade` re-verifies `now >= executable_after` on every call |
| Admin shortens the window to rush an upgrade | `set_upgrade_delay` is bounded to `[MIN, MAX]`; it can never go below 48 h, and a lowered delay only applies to *future* proposals — an in-flight proposal keeps its original `executable_after` |
| No record of who acted | `UpgradeProposal.proposed_by` plus the `upgrade_*` events give a full on-chain audit trail |

**Safe vs. sensitive delay changes:** *raising* `MIN`-bounded delay is always
safe (it only lengthens scrutiny). *Lowering* the configured delay shortens the
community veto window and should only be done with broad community consensus.

### What monitors should watch

Subscribe to the `upgrade_proposed` event (or poll `get_pending_upgrade`). On a
new proposal, verify the committed `new_wasm_hash` against a reviewed,
reproducible build before `executable_after`. An unexpected proposal — or one
whose hash does not match a published, audited build — is the signal to raise
an alarm and, if warranted, push for a `veto_upgrade`.

## Bounty Program

There is currently no formal bug bounty program.  Outstanding security reports will be credited in the release notes and can be listed in your portfolio with our written consent.

## Disclosure Policy

When a vulnerability is confirmed and a fix is ready, we will:

1. Deploy the patched contract to testnet.
2. Notify downstream teams (`api`, `dashboard`) with the new `CONTRACT_ID`.
3. Publish a post-mortem in the GitHub Releases section.
4. Credit the reporter (unless they prefer to remain anonymous).
