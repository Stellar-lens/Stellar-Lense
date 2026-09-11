import { describe, expect, it } from "vitest";
import { AlertExecutor, ExecuteExecutor } from "../src/engine/executor.js";

const INTENT = { side: "buy" as const, time: "t0", price: 1, sizePct: 1, reason: "test" };

describe("Phase 2/3 executor stubs", () => {
  it("AlertExecutor.execute throws, naming Phase 2", async () => {
    await expect(new AlertExecutor().execute(INTENT)).rejects.toThrow(/Phase 2/);
  });

  it("ExecuteExecutor.execute throws, naming Phase 3 and non-custodial Soroban", async () => {
    await expect(new ExecuteExecutor().execute(INTENT)).rejects.toThrow(/Phase 3/);
    await expect(new ExecuteExecutor().execute(INTENT)).rejects.toThrow(/Soroban/);
  });

  it("onCandle is a safe no-op on both stubs", () => {
    const candle = { time: "t0", open: 1, high: 1, low: 1, close: 1, volume: 1, trades: 1 };
    expect(() => new AlertExecutor().onCandle(candle)).not.toThrow();
    expect(() => new ExecuteExecutor().onCandle(candle)).not.toThrow();
  });
});
