import type { DataSource } from "../data/candle-source.js";
import { crossesAbove, crossesBelow, IndicatorSet } from "../strategy/indicators.js";
import type { Strategy } from "../strategy/schema.js";
import type { Candle, OrderIntent } from "../types.js";
import type { Executor } from "./executor.js";

/**
 * The one engine all three phases share (plan §4.2). It knows how to turn
 * candles + a strategy's rules into `OrderIntent`s, and it hands each
 * intent to whatever `Executor` it was constructed with — it never
 * branches on `executor.mode`. Swap `SimulateExecutor` for a no-op stub and
 * this still compiles and runs; that's the check that the engine hasn't
 * accidentally grown simulate-only assumptions.
 */
export class StrategyEngine {
  constructor(
    private readonly strategy: Strategy,
    private readonly executor: Executor,
  ) {}

  async run(dataSource: DataSource): Promise<void> {
    const indicators = new IndicatorSet(this.strategy.indicators);

    for await (const candle of dataSource.candles()) {
      indicators.update(candle.close);

      for (const rule of this.strategy.rules) {
        const fired =
          rule.when === "crosses_above"
            ? crossesAbove(
                indicators.previousValue(rule.left),
                indicators.previousValue(rule.right),
                indicators.currentValue(rule.left),
                indicators.currentValue(rule.right),
              )
            : crossesBelow(
                indicators.previousValue(rule.left),
                indicators.previousValue(rule.right),
                indicators.currentValue(rule.left),
                indicators.currentValue(rule.right),
              );

        if (!fired) continue;

        const intent: OrderIntent = {
          side: rule.action,
          time: candle.time,
          price: candle.close,
          sizePct: rule.sizePct,
          reason: `${rule.left} ${rule.when} ${rule.right}`,
        };
        await this.executor.execute(intent);
      }

      // Marked after this candle's trades settle, so the equity point for
      // candle N reflects candle N's fills, not N-1's — otherwise a fill on
      // the final candle never appears in the curve and drawdown troughs
      // are shifted one bar late.
      await this.executor.onCandle(candle);
    }
  }

  /** Exposed for tests that need to assert on a single candle's effect
   * without constructing a DataSource. */
  static async runCandles(
    strategy: Strategy,
    executor: Executor,
    candles: Candle[],
  ): Promise<void> {
    const engine = new StrategyEngine(strategy, executor);
    await engine.run({
      async *candles() {
        yield* candles;
      },
    });
  }
}
