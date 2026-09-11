import type { Candle, OrderIntent } from "../types.js";

/**
 * The three phases from docs/stellar-lens-project-plan.md §4.2 share one
 * strategy engine, distinguished only by which Executor is plugged in:
 *
 *   - "simulate" (Phase 1, implemented here): paper-fill against historical
 *     candles, no real funds, tracks a simulated portfolio.
 *   - "alert"    (Phase 2, stub): dispatch a signal (dashboard/webhook/
 *     Telegram) wired to live risk scores; never places an order.
 *   - "execute"  (Phase 3, stub): place a real order non-custodially via the
 *     user's own wallet or a Soroban session-key contract scoped to defined
 *     limits — the bot never holds user private keys.
 */
export type ExecutionMode = "simulate" | "alert" | "execute";

/** Discriminated union so each mode can report what actually happened
 * without forcing the other modes into a shape that doesn't fit them:
 * a fill has a price and quantity, an alert has neither, and an on-chain
 * submission may be pending confirmation rather than settled yet. */
export type ExecutionResult =
  | { status: "filled"; price: number; quantity: number; fee: number; time: string }
  | { status: "rejected"; reason: string }
  | { status: "dispatched"; channel: string }
  | { status: "pending"; reference: string };

/**
 * The pluggable execution boundary. StrategyEngine talks to this interface
 * only — it never branches on `mode` itself, so switching phases is a
 * matter of swapping which Executor gets constructed, not editing the
 * engine or the strategy DSL.
 */
export interface Executor {
  readonly mode: ExecutionMode;

  /** Called once per candle close, before rule evaluation, regardless of
   * whether a signal fires. Lets an executor do mode-specific bookkeeping
   * that isn't tied to a trade — e.g. SimulateExecutor marks its equity
   * curve to market here even on bars with no order. */
  onCandle(candle: Candle): void | Promise<void>;

  /** Called when the strategy's rules produce a signal. */
  execute(intent: OrderIntent): Promise<ExecutionResult>;
}

interface ClosedTrade {
  entryTime: string;
  exitTime: string;
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  pnl: number;
}

interface EquityPoint {
  time: string;
  equity: number;
}

export interface SimulateReport {
  initialCash: number;
  finalCash: number;
  finalPositionQuantity: number;
  equityCurve: EquityPoint[];
  closedTrades: ClosedTrade[];
}

/**
 * Phase 1's only implemented executor. Long-flat only (no shorting, no
 * pyramiding a position) — simplest thing that produces a meaningful
 * backtest; buys are rejected while already in a position and sells are
 * rejected while flat, rather than silently no-op'ing, so a bad strategy
 * (e.g. two buy rules that both fire) is visible in the results instead of
 * quietly losing signals.
 */
export class SimulateExecutor implements Executor {
  readonly mode = "simulate" as const;

  private cash: number;
  private positionQuantity = 0;
  private entryPrice = 0;
  private entryFee = 0;
  private entryTime = "";
  private readonly equityCurve: EquityPoint[] = [];
  private readonly closedTrades: ClosedTrade[] = [];

  constructor(
    private readonly initialCash: number,
    private readonly feeBps: number = 0,
  ) {
    this.cash = initialCash;
  }

  onCandle(candle: Candle): void {
    this.equityCurve.push({
      time: candle.time,
      equity: this.cash + this.positionQuantity * candle.close,
    });
  }

  async execute(intent: OrderIntent): Promise<ExecutionResult> {
    if (intent.side === "buy") {
      if (this.positionQuantity > 0) {
        return { status: "rejected", reason: "already in position" };
      }
      const deployable = this.cash * intent.sizePct;
      const fee = (deployable * this.feeBps) / 10_000;
      const quantity = (deployable - fee) / intent.price;
      if (quantity <= 0) {
        return { status: "rejected", reason: "insufficient cash for order size" };
      }
      this.cash -= deployable;
      this.positionQuantity = quantity;
      this.entryPrice = intent.price;
      this.entryFee = fee;
      this.entryTime = intent.time;
      return { status: "filled", price: intent.price, quantity, fee, time: intent.time };
    }

    if (this.positionQuantity <= 0) {
      return { status: "rejected", reason: "no position to sell" };
    }
    const quantity = this.positionQuantity * intent.sizePct;
    const proceeds = quantity * intent.price;
    const fee = (proceeds * this.feeBps) / 10_000;
    this.cash += proceeds - fee;

    const entryCost = this.entryPrice * quantity + this.entryFee * intent.sizePct;
    this.closedTrades.push({
      entryTime: this.entryTime,
      exitTime: intent.time,
      entryPrice: this.entryPrice,
      exitPrice: intent.price,
      quantity,
      pnl: proceeds - fee - entryCost,
    });
    this.positionQuantity -= quantity;

    return { status: "filled", price: intent.price, quantity, fee, time: intent.time };
  }

  /** Simulate-specific: not part of the Executor interface, since "returns
   * and drawdown" only make sense for a mode with a simulated portfolio.
   * The CLI/report layer reads this directly rather than the engine
   * routing it through, keeping StrategyEngine itself report-agnostic too. */
  getReport(): SimulateReport {
    return {
      initialCash: this.initialCash,
      finalCash: this.cash,
      finalPositionQuantity: this.positionQuantity,
      equityCurve: this.equityCurve,
      closedTrades: this.closedTrades,
    };
  }
}

/**
 * Phase 2 stub. Not implemented yet — per the plan, this wires the same
 * signals into the dashboard/webhook/Telegram and existing risk scores,
 * without placing an order. Deliberately throws rather than silently
 * no-op'ing so a caller can't mistake "not implemented" for "no signals
 * fired".
 */
export class AlertExecutor implements Executor {
  readonly mode = "alert" as const;

  onCandle(_candle: Candle): void {
    // No portfolio to mark to market in alert mode.
  }

  async execute(_intent: OrderIntent): Promise<ExecutionResult> {
    throw new Error(
      "AlertExecutor is not implemented yet (Phase 2, plan §4.2): dispatch " +
        "signals to dashboard/webhook/Telegram, wired to risk scores.",
    );
  }
}

/**
 * Phase 3 stub. Not implemented yet — per the plan, execution is
 * non-custodial: the bot never holds user private keys. Orders place
 * through the user's own wallet (Freighter/Albedo) or a Soroban
 * session-key contract scoped to defined limits (max amount, asset
 * allowlist, time window), revocable anytime.
 */
export class ExecuteExecutor implements Executor {
  readonly mode = "execute" as const;

  onCandle(_candle: Candle): void {
    // Real balances live on-chain; nothing to mark to market locally.
  }

  async execute(_intent: OrderIntent): Promise<ExecutionResult> {
    throw new Error(
      "ExecuteExecutor is not implemented yet (Phase 3, plan §4.2): submit " +
        "via a non-custodial Soroban session-key contract, never a held key.",
    );
  }
}
