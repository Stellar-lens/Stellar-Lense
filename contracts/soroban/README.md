# contracts/soroban

On-chain risk registry contract(s). Migrates from `Ledgerlens-contract`.

Its own Cargo workspace, independent of the pnpm/uv workspaces elsewhere in
the monorepo — `contracts/soroban/Cargo.toml` is the workspace root, with
member crates added under this directory as they migrate in (`members = []`
for now). See `docs/stellar-lens-project-plan.md` §2, and §3 for the
rebrand checklist (`ledgerlens-score` contract name/symbol, etc.).

Not yet migrated — this is skeleton only.
