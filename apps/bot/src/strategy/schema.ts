import { z } from "zod";

/** Declarative strategy DSL: indicators + threshold/crossover rules. Not a
 * scripting language — the roadmap only calls for "a strategy defined in a
 * simple config", and a small, validated grammar is easier to reason about
 * (and to eventually expose safely in a UI) than an embedded script. */

const IndicatorSchema = z.object({
  id: z.string().min(1),
  type: z.enum(["sma"]),
  period: z.number().int().positive(),
});

const RuleSchema = z.object({
  when: z.enum(["crosses_above", "crosses_below"]),
  left: z.string().min(1),
  right: z.string().min(1),
  action: z.enum(["buy", "sell"]),
  sizePct: z.number().min(0).max(1).default(1),
});

const RiskSchema = z.object({
  initialCash: z.number().positive(),
  feeBps: z.number().min(0).default(0),
});

export const StrategySchema = z
  .object({
    name: z.string().min(1),
    pair: z.object({
      base: z.string().min(1),
      counter: z.string().min(1),
    }),
    indicators: z.array(IndicatorSchema).min(1),
    rules: z.array(RuleSchema).min(1),
    risk: RiskSchema,
  })
  .superRefine((strategy, ctx) => {
    const ids = new Set(strategy.indicators.map((i) => i.id));
    for (const [i, rule] of strategy.rules.entries()) {
      for (const side of ["left", "right"] as const) {
        if (!ids.has(rule[side])) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["rules", i, side],
            message: `rule references unknown indicator id ${JSON.stringify(rule[side])}`,
          });
        }
      }
      // SimulateExecutor's long-flat model only tracks a single entryPrice/
      // entryFee for the open position. A partial sell (sizePct < 1) would
      // decrement the quantity without adjusting those, so a later buy
      // would be rejected as "already in position" (residual left over)
      // and any further partial exit would misreport entryTime/cost basis.
      // Rejected at config-validation time rather than left as a silent
      // runtime bug — full exits only until the executor tracks lots.
      if (rule.action === "sell" && rule.sizePct !== 1) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["rules", i, "sizePct"],
          message:
            "sell rules must use sizePct: 1 (full exit) — partial exits aren't " +
            "supported by SimulateExecutor's long-flat position tracking yet",
        });
      }
    }
  });

export type Strategy = z.infer<typeof StrategySchema>;
export type Indicator = z.infer<typeof IndicatorSchema>;
export type Rule = z.infer<typeof RuleSchema>;
