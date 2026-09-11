# apps/bot

Stellar Lense trading bot: one strategy engine, pluggable execution mode,
built in three phases (see `docs/stellar-lens-project-plan.md` §4.2 for the
full breakdown and the non-custodial Phase 3 rationale):

1. **Backtesting engine** (implemented here) — historical data, no real funds.
2. **Signal/alert bot** (stubbed) — live data, no execution, wired to risk scores.
3. **Auto-execution** (stubbed) — non-custodial, scoped Soroban session permissions.

## Architecture

`StrategyEngine` (`src/engine/engine.ts`) turns candles + a strategy's rules
into `OrderIntent`s and hands each one to an `Executor` (`src/engine/executor.ts`).
The engine never branches on which mode it's running in — it only knows the
`Executor` interface:

```ts
interface Executor {
  readonly mode: "simulate" | "alert" | "execute";
  onCandle(candle: Candle): void | Promise<void>;
  execute(intent: OrderIntent): Promise<ExecutionResult>;
}
```

- `SimulateExecutor` — the only implementation today. Paper-fills against
  the candle close, long-flat only (no shorting/pyramiding), and tracks a
  simulated portfolio (cash, position, equity curve, closed trades).
- `AlertExecutor` / `ExecuteExecutor` — stubs whose `execute()` throws,
  naming the phase and what it needs. They exist so the engine and CLI
  plumbing for Phases 2/3 are already wired; only the executor body is
  missing.

Swapping executors is the only thing that changes between phases — not the
engine, not the strategy DSL, not the data source interface.

## Strategy DSL

A small declarative YAML grammar (indicators + crossover rules), not a
scripting language — see `strategies/sma-crossover.example.yaml`. Validated
with zod (`src/strategy/schema.ts`), including that every rule references an
indicator id that actually exists.

## Historical data

`apps/bot` (TypeScript) can't import `data/pipelines`' Python ingestion
directly, so `data/pipelines/scripts/export_trades_for_bot.py` is the reuse
boundary: it drives the real `ingestion.historical_loader.load_trades()`
against Horizon, aggregates trades into OHLCV candles, and writes them as
newline-delimited JSON. `NdjsonCandleSource` (`src/data/candle-source.ts`)
reads that format as an `AsyncIterable<Candle>` — the same shape a live feed
would yield for Phase 2, so `StrategyEngine.run()`'s loop doesn't change.

`fixtures/xlm-usdc-5m.ndjson` is a real, small (45-candle) export from live
Horizon (XLM/USDC, Circle issuer), committed so the sample backtest and
tests run offline and reproducibly. Regenerate or extend it with:

```bash
cd data/pipelines
python -m scripts.export_trades_for_bot \
  --base XLM --counter USDC \
  --counter-issuer GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN \
  --resolution 5m --limit 8000 \
  --output ../../apps/bot/fixtures/xlm-usdc-5m.ndjson
```

## Running a backtest

```bash
pnpm --filter @stellar-lense/bot backtest -- \
  --strategy strategies/sma-crossover.example.yaml \
  --data fixtures/xlm-usdc-5m.ndjson
```

Prints the strategy name, pair, and metrics as JSON: total (not annualized)
return, max drawdown (peak-to-trough on the mark-to-market equity curve, not
realized PnL), win rate (over closed round-trip positions), closed trade
count, and final equity.

`--mode alert` / `--mode execute` run the same engine against the same data
and strategy, and fail loudly with a "not implemented" error naming the
phase, rather than silently doing nothing.
