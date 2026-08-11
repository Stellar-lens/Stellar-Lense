import { test } from "node:test";
import assert from "node:assert/strict";
import { scoreClass, scoreLabel, pill, formatTs, shortenWallet } from "../dashboard/js/formatters.js";

test("scoreClass buckets scores into low/medium/high", () => {
  assert.equal(scoreClass(0), "low");
  assert.equal(scoreClass(39), "low");
  assert.equal(scoreClass(40), "medium");
  assert.equal(scoreClass(69), "medium");
  assert.equal(scoreClass(70), "high");
  assert.equal(scoreClass(100), "high");
});

test("scoreLabel matches scoreClass thresholds", () => {
  assert.equal(scoreLabel(10), "Low Risk");
  assert.equal(scoreLabel(50), "Medium Risk");
  assert.equal(scoreLabel(90), "High Risk");
});

test("pill renders a span with the right class and score", () => {
  assert.equal(pill(82), '<span class="score-pill high">82</span>');
});

test("shortenWallet keeps the first 12 and last 4 characters", () => {
  const wallet = "GCEZWKCA5VLDNRLN3RPRJMRZOX3Z6G5CHCGMJUI6TUOHTFKDMHH0PMJK";
  assert.equal(shortenWallet(wallet), "GCEZWKCA5VLD…PMJK");
});

test("formatTs produces a non-empty, locale-formatted string", () => {
  const formatted = formatTs("2026-06-01T00:04:00");
  assert.ok(formatted.length > 0);
  assert.doesNotMatch(formatted, /Invalid Date/);
});
