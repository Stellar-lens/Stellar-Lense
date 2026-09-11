import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { scoreClass } from "../dashboard/js/formatters.js";

const css = readFileSync(new URL("../dashboard/styles.css", import.meta.url), "utf8");

// Matches "--foo:" (a definition) but not "var(--foo)" (a usage) — a colon
// immediately follows a definition, a ")" follows a var() reference.
const definedTokens = new Set([...css.matchAll(/--[\w-]+(?=\s*:)/g)].map((m) => m[0]));

test("styles.css defines at least the core token groups", () => {
  for (const token of ["--bg", "--surface", "--text", "--accent", "--radius", "--space-4"]) {
    assert.ok(definedTokens.has(token), `expected ${token} to be defined in styles.css`);
  }
});

test("every scoreClass() output has a matching color token", () => {
  // render.js builds `var(--${scoreClass(score)})` and `.score-pill.${scoreClass(score)}`
  // dynamically — nothing statically references "--low"/"--medium"/"--high", so a typo
  // or a token rename in styles.css won't show up as a lint error. This is the guard.
  const representativeScores = [0, 39, 40, 69, 70, 100];
  const classes = new Set(representativeScores.map(scoreClass));
  assert.deepEqual([...classes].sort(), ["high", "low", "medium"]);

  for (const cls of classes) {
    assert.ok(
      definedTokens.has(`--${cls}`),
      `render.js's asset-avg color does \`var(--${cls})\`, but styles.css has no --${cls} token`,
    );
    assert.ok(
      definedTokens.has(`--${cls}-bg`),
      `.score-pill.${cls} needs a --${cls}-bg background token`,
    );
  }
});
