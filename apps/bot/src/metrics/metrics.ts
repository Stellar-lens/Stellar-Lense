import type { SimulateReport } from "../engine/executor.js";

export interface BacktestMetrics {
  /** Total (not annualized) return over the whole run, as a percentage. */
  totalReturnPct: number;
  /** Largest peak-to-trough decline in mark-to-market equity, as a
   * percentage. Computed from the equity curve, not from realized trade
   * PnL — a position can be underwater between fills. */
  maxDrawdownPct: number;
  /** Fraction of closed round-trip positions with positive PnL, in [0, 1].
   * `null` if no position was ever closed. */
  winRate: number | null;
  closedTradeCount: number;
  finalEquity: number;
}

export function computeMetrics(report: SimulateReport): BacktestMetrics {
  const finalEquity =
    report.equityCurve.length > 0
      ? report.equityCurve[report.equityCurve.length - 1].equity
      : report.initialCash;

  const totalReturnPct = ((finalEquity - report.initialCash) / report.initialCash) * 100;

  let peak = report.initialCash;
  let maxDrawdownPct = 0;
  for (const point of report.equityCurve) {
    peak = Math.max(peak, point.equity);
    const drawdownPct = ((peak - point.equity) / peak) * 100;
    maxDrawdownPct = Math.max(maxDrawdownPct, drawdownPct);
  }

  const winRate =
    report.closedTrades.length === 0
      ? null
      : report.closedTrades.filter((t) => t.pnl > 0).length / report.closedTrades.length;

  return {
    totalReturnPct,
    maxDrawdownPct,
    winRate,
    closedTradeCount: report.closedTrades.length,
    finalEquity,
  };
}
