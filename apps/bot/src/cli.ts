#!/usr/bin/env node
import { NdjsonCandleSource } from "./data/candle-source.js";
import { StrategyEngine } from "./engine/engine.js";
import type { ExecutionMode } from "./engine/executor.js";
import { AlertExecutor, ExecuteExecutor, SimulateExecutor } from "./engine/executor.js";
import { computeMetrics } from "./metrics/metrics.js";
import { loadStrategyFile } from "./strategy/loader.js";

function parseArgs(argv: string[]): Record<string, string> {
  // `pnpm run <script> -- --foo bar` forwards the "--" separator itself on
  // this pnpm version rather than stripping it; drop a leading one so both
  // `pnpm backtest -- --strategy ...` and a direct `tsx src/cli.ts
  // --strategy ...` invocation work.
  const rest = argv[0] === "--" ? argv.slice(1) : argv;

  const args: Record<string, string> = {};
  for (let i = 0; i < rest.length; i += 2) {
    const key = rest[i]?.replace(/^--/, "");
    const value = rest[i + 1];
    if (!key || value === undefined) {
      throw new Error(`Malformed argument near ${JSON.stringify(rest[i])}`);
    }
    args[key] = value;
  }
  return args;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const strategyPath = args.strategy;
  const dataPath = args.data;
  const mode = (args.mode ?? "simulate") as ExecutionMode;

  if (!strategyPath || !dataPath) {
    console.error(
      "Usage: backtest --strategy <strategy.yaml> --data <candles.ndjson> [--mode simulate]",
    );
    process.exit(1);
  }

  const strategy = loadStrategyFile(strategyPath);
  const dataSource = new NdjsonCandleSource(dataPath);

  if (mode !== "simulate") {
    // AlertExecutor/ExecuteExecutor exist so the engine and CLI plumbing
    // are already in place for Phases 2/3 — only their execute() throws.
    const executor = mode === "alert" ? new AlertExecutor() : new ExecuteExecutor();
    const engine = new StrategyEngine(strategy, executor);
    await engine.run(dataSource);
    return;
  }

  const executor = new SimulateExecutor(strategy.risk.initialCash, strategy.risk.feeBps);
  const engine = new StrategyEngine(strategy, executor);
  await engine.run(dataSource);

  const report = executor.getReport();
  const metrics = computeMetrics(report);

  console.log(
    JSON.stringify(
      {
        strategy: strategy.name,
        pair: strategy.pair,
        mode,
        metrics: {
          totalReturnPct: round(metrics.totalReturnPct),
          maxDrawdownPct: round(metrics.maxDrawdownPct),
          winRate: metrics.winRate === null ? null : round(metrics.winRate * 100),
          closedTradeCount: metrics.closedTradeCount,
          finalEquity: round(metrics.finalEquity),
        },
      },
      null,
      2,
    ),
  );
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
