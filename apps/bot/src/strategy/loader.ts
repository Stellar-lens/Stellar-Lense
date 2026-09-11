import { readFileSync } from "node:fs";
import { load as parseYaml } from "js-yaml";
import { StrategySchema, type Strategy } from "./schema.js";

export function loadStrategyFile(path: string): Strategy {
  const raw = readFileSync(path, "utf-8");
  const parsed = parseYaml(raw);
  const result = StrategySchema.safeParse(parsed);
  if (!result.success) {
    const issues = result.error.issues
      .map((issue) => `  - ${issue.path.join(".")}: ${issue.message}`)
      .join("\n");
    throw new Error(`Invalid strategy config at ${path}:\n${issues}`);
  }
  return result.data;
}
