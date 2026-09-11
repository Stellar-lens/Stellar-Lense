import { z } from "zod";

/** One OHLCV bar. Produced today by data/pipelines' export script for
 * historical replay; Phase 2 will source the same shape from a live feed. */
export const CandleSchema = z.object({
  time: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number(),
  trades: z.number().int().nonnegative(),
});
export type Candle = z.infer<typeof CandleSchema>;

/** A trading decision the strategy's rules produced for one candle. Carries
 * no notion of "how" it gets carried out — that's the Executor's job. */
export interface OrderIntent {
  side: "buy" | "sell";
  time: string;
  /** Reference price at signal time (the candle close). What an executor
   * actually fills at may differ (slippage, partial fill, rejection). */
  price: number;
  /** Fraction of deployable capital/position this rule targets, in [0, 1]. */
  sizePct: number;
  /** Human-readable justification, e.g. "fast crosses_above slow". */
  reason: string;
}
