# contracts/soroban

Soroban contracts for Stellar Lense. Rust 1.81 is pinned in
`rust-toolchain.toml` (newer rustc emits Wasm features the Soroban host
rejects for soroban-sdk 21).

| Crate | What it is | Deployed |
|---|---|---|
| [`contracts/stellar-lense-registry`](contracts/stellar-lense-registry) | The risk-score registry: authorised signers publish wallet and pair scores; anyone reads them or calls the `check` risk gate. | testnet, see [`/deployments/testnet.json`](../../deployments/testnet.json) |
| [`contracts/mock-amm`](contracts/mock-amm) | Example integration: an AMM-shaped contract that refuses swaps the registry's gate rejects. | testnet (demo) |
| [`experimental/`](experimental) | The original 13.5k-line `stellar-lense-score` contract and its tooling. Separate workspace; not built by CI, not deployed. | no |

## Registry API

| Function | Who | What |
|---|---|---|
| `initialize(admin, signers, threshold)` | admin, once | Set admin, publishing signers and the `is_flagged` threshold. |
| `submit_score(signer, wallet, pair, score, confidence, method, as_of)` | signer | Write one wallet's score. Rejects values > 100 and anything older than what's stored. |
| `submit_scores(signer, Vec<ScoreInput>)` | signer | Up to 50 scores, all-or-nothing. |
| `submit_pair_score(signer, pair, average, max, flagged, total, as_of)` | signer | Write a pair's aggregate. |
| `get_score(wallet, pair)` / `get_pair_score(pair)` | anyone | Latest stored values, or none. |
| `is_flagged(wallet, pair)` | anyone | Score exists and is ≥ threshold. |
| `check(wallet, pair, max_score, max_age_secs)` | anyone | Risk gate: `Allow`, `HighRisk`, `NoScore` or `Stale`. The caller picks its own bar and freshness, and decides fail-open vs fail-closed for `NoScore`/`Stale`. |
| `pause` / `unpause` | admin | Stop or resume writes. Reads keep working. |
| `add_signer` / `remove_signer` | admin | The last signer can't be removed. |
| `set_threshold` | admin | 0-100. |
| `propose_admin` → `accept_admin` | admin → nominee | Two-step rotation; the nominee must sign to accept. |
| `upgrade(new_wasm_hash)` | admin | Replace the code, keeping storage. |
| `admin`, `pending_admin`, `is_signer`, `is_paused`, `threshold`, `version` | anyone | Introspection. |

Every write emits an event (`score`, `pair`, `paused`, `sig_add`,
`sig_rm`, `thresh`, `adm_prop`, `adm_acc`, `upgrade`, `init`). Stored
entries are extended to ~30 days of TTL on every write.

Pairs use the same identifier as the API, e.g.
`XLM/USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN`.

## Develop, deploy, verify

```bash
cargo test --workspace                       # registry + mock-amm tests
cargo clippy --workspace --all-targets -- -D warnings

# Build, deploy and initialise on testnet; writes /deployments/testnet.json.
# Generates and friendbot-funds keys into /.secrets/testnet-keys.json
# (gitignored) on first run.
uv run --package stellar-lense-core --extra chain \
    python contracts/soroban/deploy/deploy_testnet.py --with-mock-amm

# Read scores back (what the nightly CI job runs; read-only, no keys).
uv run --package stellar-lense-core --extra chain \
    python contracts/soroban/deploy/check_testnet.py
```

Scores get onto the registry through the pipeline: set
`REGISTRY_CONTRACT_ID` and `PUBLISHER_SECRET` and `python -m pipeline run`
publishes each new scoring run (pair aggregates plus the top 10 wallets per
pair). See `packages/core/pipeline/publish.py`.
