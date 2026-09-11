import { describe, expect, it } from "vitest";
import { StrategyEngine } from "../src/engine/engine.js";
import type { Executor, ExecutionResult } from "../src/engine/executor.js";
import { SimulateExecutor } from "../src/engine/executor.js";
import type { Strategy } from "../src/strategy/schema.js";
import { StrategySchema } from "../src/strategy/schema.js";
import type { Candle, OrderIntent } from "../src/types.js";
import { computeMetrics } from "../src/metrics/metrics.js";

const STRATEGY: Strategy = StrategySchema.parse({
  name: "test-crossover",
  pair: { base: "XLM", counter: "USDC" },
  indicators: [
    { id: "fast", type: "sma", period: 2 },
    { id: "slow", type: "sma", period: 3 },
  ],
  rules: [
    { when: "crosses_above", left: "fast", right: "slow", action: "buy", sizePct: 1 },
    { when: "crosses_below", left: "fast", right: "slow", action: "sell", sizePct: 1 },
  ],
  risk: { initialCash: 1000, feeBps: 0 },
});

// Closes chosen so fast(2)/slow(3) SMA produce exactly one crossing each way,
// hand-verified: buy fires at t3 (close 20), sell fires at t6 (close 5).
const CLOSES = [10, 10, 10, 20, 20, 20, 5, 5, 5];
const CANDLES: Candle[] = CLOSES.map((close, i) => ({
  time: `t${i}`,
  open: close,
  high: close,
  low: close,
  close,
  volume: 1,
  trades: 1,
}));

describe("StrategyEngine mode-agnosticism", () => {
  it("runs identically whether given SimulateExecutor or a bare-bones stub Executor", async () => {
    // If StrategyEngine had accreted simulate-specific assumptions, this
    // stub — which implements nothing but the Executor interface — would
    // fail to type-check or throw at runtime. It does neither.
    class StubExecutor implements Executor {
      readonly mode = "simulate" as const;
      calls: OrderIntent[] = [];
      onCandle(): void {}
      async execute(intent: OrderIntent): Promise<ExecutionResult> {
        this.calls.push(intent);
        return { status: "dispatched", channel: "test" };
      }
    }

    const stub = new StubExecutor();
    await StrategyEngine.runCandles(STRATEGY, stub, CANDLES);

    expect(stub.calls).toHaveLength(2);
    expect(stub.calls[0]).toMatchObject({ side: "buy", price: 20 });
    expect(stub.calls[1]).toMatchObject({ side: "sell", price: 5 });
  });
});

describe("StrategyEngine + SimulateExecutor end to end", () => {
  it("produces the hand-computed equity curve, trade, and metrics", async () => {
    const executor = new SimulateExecutor(1000, 0);
    await StrategyEngine.runCandles(STRATEGY, executor, CANDLES);

    const report = executor.getReport();

    // Buy 50 units at 20 (all cash deployed), sell all 50 at 5.
    expect(report.closedTrades).toHaveLength(1);
    expect(report.closedTrades[0]).toMatchObject({
      entryPrice: 20,
      exitPrice: 5,
      quantity: 50,
      pnl: -750,
    });
    expect(report.finalCash).toBe(250);
    expect(report.finalPositionQuantity).toBe(0);

    const metrics = computeMetrics(report);
    expect(metrics.totalReturnPct).toBeCloseTo(-75, 10);
    expect(metrics.maxDrawdownPct).toBeCloseTo(75, 10);
    expect(metrics.winRate).toBe(0);
    expect(metrics.closedTradeCount).toBe(1);
  });

  it("rejects a buy while already in a position instead of pyramiding", async () => {
    const executor = new SimulateExecutor(1000, 0);
    const first = await executor.execute({
      side: "buy",
      time: "t0",
      price: 10,
      sizePct: 1,
      reason: "test",
    });
    const second = await executor.execute({
      side: "buy",
      time: "t1",
      price: 10,
      sizePct: 1,
      reason: "test",
    });
    expect(first.status).toBe("filled");
    expect(second).toMatchObject({ status: "rejected" });
  });

  it("rejects a sell while flat", async () => {
    const executor = new SimulateExecutor(1000, 0);
    const result = await executor.execute({
      side: "sell",
      time: "t0",
      price: 10,
      sizePct: 1,
      reason: "test",
    });
    expect(result).toMatchObject({ status: "rejected", reason: "no position to sell" });
  });

  it("marks the final equity point after a trade that fires on the last candle", async () => {
    // Same crossover trace as above, truncated right after the sell signal
    // (idx6) so it fires on the final candle — the case that would expose
    // onCandle() being called before that candle's trade settles instead
    // of after: with fees, the pre-trade mark-to-market value and the
    // post-trade realized value differ, so a stale equity point is visible.
    const feeBps = 100; // 1%
    const truncatedCandles = CANDLES.slice(0, 7); // idx0..idx6, sell fires on idx6
    const executor = new SimulateExecutor(1000, feeBps);
    await StrategyEngine.runCandles(STRATEGY, executor, truncatedCandles);

    const report = executor.getReport();
    const lastClose = truncatedCandles[truncatedCandles.length - 1].close;

    expect(report.closedTrades).toHaveLength(1);
    // Buy: deployable 1000, fee 10, quantity (1000-10)/20 = 49.5.
    // Sell: proceeds 49.5*5=247.5, fee 2.475, cash = 245.025.
    expect(report.finalCash).toBeCloseTo(245.025, 6);
    expect(report.finalPositionQuantity).toBe(0);

    const lastEquityPoint = report.equityCurve[report.equityCurve.length - 1];
    expect(lastEquityPoint.equity).toBeCloseTo(245.025, 6);

    // The general invariant: the last equity point must equal cash plus the
    // remaining position marked at the last known close — never a value
    // from before that candle's own trade.
    expect(lastEquityPoint.equity).toBeCloseTo(
      report.finalCash + report.finalPositionQuantity * lastClose,
      6,
    );

    const metrics = computeMetrics(report);
    expect(metrics.finalEquity).toBeCloseTo(245.025, 6);
  });
});
