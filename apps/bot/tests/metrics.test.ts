import { describe, expect, it } from "vitest";
import type { SimulateReport } from "../src/engine/executor.js";
import { computeMetrics } from "../src/metrics/metrics.js";

describe("computeMetrics", () => {
  it("computes total return, peak-to-trough drawdown, and win rate by hand", () => {
    // Equity curve: 1000 -> 1100 -> 900 -> 1200 -> 1250.
    // Peaks:                1000    1100    1100    1200    1250
    // Drawdown %:              0       0   18.1818%     0       0
    const report: SimulateReport = {
      initialCash: 1000,
      finalCash: 1250,
      finalPositionQuantity: 0,
      equityCurve: [
        { time: "t0", equity: 1000 },
        { time: "t1", equity: 1100 },
        { time: "t2", equity: 900 },
        { time: "t3", equity: 1200 },
        { time: "t4", equity: 1250 },
      ],
      closedTrades: [
        { entryTime: "a", exitTime: "b", entryPrice: 1, exitPrice: 1.1, quantity: 1, pnl: 100 },
        { entryTime: "c", exitTime: "d", entryPrice: 1, exitPrice: 0.9, quantity: 1, pnl: -50 },
        { entryTime: "e", exitTime: "f", entryPrice: 1, exitPrice: 1.075, quantity: 1, pnl: 75 },
      ],
    };

    const metrics = computeMetrics(report);

    expect(metrics.totalReturnPct).toBeCloseTo(25, 10); // (1250-1000)/1000 * 100
    expect(metrics.maxDrawdownPct).toBeCloseTo((200 / 1100) * 100, 10); // (1100-900)/1100
    expect(metrics.winRate).toBeCloseTo(2 / 3, 10);
    expect(metrics.closedTradeCount).toBe(3);
    expect(metrics.finalEquity).toBe(1250);
  });

  it("returns winRate null and 0 drawdown/return for a flat, tradeless run", () => {
    const report: SimulateReport = {
      initialCash: 1000,
      finalCash: 1000,
      finalPositionQuantity: 0,
      equityCurve: [{ time: "t0", equity: 1000 }],
      closedTrades: [],
    };

    const metrics = computeMetrics(report);

    expect(metrics.totalReturnPct).toBe(0);
    expect(metrics.maxDrawdownPct).toBe(0);
    expect(metrics.winRate).toBeNull();
  });

  it("falls back to initialCash for return/drawdown when there's no equity history", () => {
    const report: SimulateReport = {
      initialCash: 500,
      finalCash: 500,
      finalPositionQuantity: 0,
      equityCurve: [],
      closedTrades: [],
    };

    const metrics = computeMetrics(report);
    expect(metrics.finalEquity).toBe(500);
    expect(metrics.totalReturnPct).toBe(0);
  });
});
