import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadStrategyFile } from "../src/strategy/loader.js";

function writeYaml(contents: string): string {
  const dir = mkdtempSync(join(tmpdir(), "bot-strategy-"));
  const path = join(dir, "strategy.yaml");
  writeFileSync(path, contents);
  return path;
}

describe("loadStrategyFile", () => {
  it("loads and validates the committed sample strategy", () => {
    const strategy = loadStrategyFile("strategies/sma-crossover.example.yaml");
    expect(strategy.name).toBe("sma-crossover-xlm-usdc");
    expect(strategy.indicators).toHaveLength(2);
    expect(strategy.rules).toHaveLength(2);
    expect(strategy.risk.initialCash).toBe(10000);
  });

  it("rejects a strategy missing a required field", () => {
    const path = writeYaml(`
name: broken
indicators:
  - id: fast
    type: sma
    period: 3
rules:
  - when: crosses_above
    left: fast
    right: slow
    action: buy
risk:
  initialCash: 1000
`);
    // Missing `pair`.
    expect(() => loadStrategyFile(path)).toThrow(/pair/);
  });

  it("rejects a rule that references an indicator id that doesn't exist", () => {
    const path = writeYaml(`
name: dangling-ref
pair:
  base: XLM
  counter: USDC
indicators:
  - id: fast
    type: sma
    period: 3
rules:
  - when: crosses_above
    left: fast
    right: slow
    action: buy
risk:
  initialCash: 1000
`);
    expect(() => loadStrategyFile(path)).toThrow(/unknown indicator id "slow"/);
  });
});
