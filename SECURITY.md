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

## Bounty Program

There is currently no formal bug bounty program.  Outstanding security reports will be credited in the release notes and can be listed in your portfolio with our written consent.

## Disclosure Policy

When a vulnerability is confirmed and a fix is ready, we will:

1. Deploy the patched contract to testnet.
2. Notify downstream teams (`api`, `dashboard`) with the new `CONTRACT_ID`.
3. Publish a post-mortem in the GitHub Releases section.
4. Credit the reporter (unless they prefer to remain anonymous).
