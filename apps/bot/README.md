# apps/bot

Stellar Lense trading bot service. New — no prior repo.

One strategy engine, pluggable execution mode, built in three phases:
1. Backtesting engine (historical data, no real funds)
2. Signal/alert bot (live data, no execution, wired to existing risk scores)
3. Auto-execution (non-custodial, scoped Soroban session permissions)

Build the execution interface as pluggable from Phase 1 even though auto-
execution is last. See `docs/stellar-lens-project-plan.md` §4.2 for the full
phase breakdown and the custodial-vs-non-custodial decision rationale.

Not yet implemented — this is skeleton only.
