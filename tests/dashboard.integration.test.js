import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const html = readFileSync(new URL("../dashboard/index.html", import.meta.url), "utf8");
const appUrl = fileURLToPath(new URL("../dashboard/js/app.js", import.meta.url));

const WALLET = "GDKRY7GNU3CJQX6FMT2BIPW5ELSZAHOV4DKRY7GNU3CJQX6FMT2BIPW5";
const PAIR = "XLM/USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN";
const OTHER_WALLET = "GBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";
const OTHER_PAIR = "XLM/YBX:GBYBXBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";

const ALERTS = [
  {
    id: "1",
    wallet: WALLET,
    asset_pair: PAIR,
    score: 91,
    reason: "round-trip trading detected",
    timestamp: "2026-06-01T04:00:00",
  },
  {
    id: "2",
    wallet: OTHER_WALLET,
    asset_pair: OTHER_PAIR,
    score: 82,
    reason: "high counterparty concentration",
    timestamp: "2026-06-01T02:00:00",
  },
];
const ASSETS = [
  { asset_pair: PAIR, average_score: 61.3, max_score: 91, flagged_wallets: 2, total_wallets: 7 },
  {
    asset_pair: OTHER_PAIR,
    average_score: 45,
    max_score: 82,
    flagged_wallets: 1,
    total_wallets: 3,
  },
];

// Fresh module graph per test (app.js runs its init() as a side effect of
// being imported), and a fresh jsdom window so tests don't leak state.
let importCounter = 0;

async function mount(fetchImpl) {
  const dom = new JSDOM(html, { url: "http://localhost/", pretendToBeVisual: true });
  const { window } = dom;

  globalThis.window = window;
  globalThis.document = window.document;
  Object.defineProperty(globalThis, "navigator", { value: window.navigator, configurable: true });
  globalThis.localStorage = window.localStorage;
  globalThis.fetch = fetchImpl;
  globalThis.AbortController = AbortController;
  globalThis.setInterval = () => 0; // never let the 60s poll fire during a test
  globalThis.clearInterval = () => {};
  globalThis.setTimeout = setTimeout;
  window.navigator.clipboard = {
    writeText: async (text) => {
      window.__copied = text;
    },
  };
  window.matchMedia = () => ({ matches: false });

  await import(`${appUrl}?t=${importCounter++}`);
  await new Promise((r) => setTimeout(r, 20)); // let the initial refreshAll() settle
  return window;
}

function jsonResponse(body, init = {}) {
  return { ok: true, status: 200, json: async () => body, ...init };
}

function defaultFetch(url) {
  const path = new URL(url).pathname + new URL(url).search;
  if (path.startsWith("/health")) return Promise.resolve(jsonResponse({ status: "ok" }));
  if (path.startsWith("/alerts/recent")) return Promise.resolve(jsonResponse(ALERTS));
  if (path.startsWith("/assets/risk-ranking")) return Promise.resolve(jsonResponse(ASSETS));
  if (path === `/score/${WALLET}/${PAIR}`) {
    return Promise.resolve(
      jsonResponse({
        wallet: WALLET,
        asset_pair: PAIR,
        score: 91,
        benford_flag: true,
        ml_flag: true,
        confidence: 88,
        timestamp: "2026-06-01T04:00:00",
      }),
    );
  }
  return Promise.resolve({
    ok: false,
    status: 404,
    statusText: "Not Found",
    json: async () => ({ detail: "Unknown asset pair" }),
  });
}

test("initial load renders stats, alerts, and assets from the API", async () => {
  const window = await mount(defaultFetch);
  assert.equal(window.document.querySelector("#stat-flagged").textContent, "2");
  assert.equal(window.document.querySelector("#stat-assets").textContent, "2");
  assert.equal(window.document.querySelector("#stat-avg").textContent, "53");
  assert.equal(window.document.querySelectorAll("#alerts-body tr").length, 2);
  assert.equal(window.document.querySelectorAll(".asset-card").length, 2);
  assert.match(window.document.querySelector("#last-updated").textContent, /^Updated /);
});

test("alerts filter narrows rows to the matching wallet/pair", async () => {
  const window = await mount(defaultFetch);
  const input = window.document.querySelector("#alerts-filter");
  input.value = "YBX";
  input.dispatchEvent(new window.Event("input"));
  assert.equal(window.document.querySelectorAll("#alerts-body tr").length, 1);
  assert.match(window.document.querySelector("#alerts-body .wallet-cell").textContent, /GBBB/);
});

test("clicking the score header toggles sort direction", async () => {
  const window = await mount(defaultFetch);
  const header = window.document.querySelector('th[data-sort-key="score"]');
  header.click();
  assert.ok(header.classList.contains("sort-asc"));
  const scores = [...window.document.querySelectorAll("#alerts-body .score-pill")].map(
    (el) => el.textContent,
  );
  assert.deepEqual(scores, ["82", "91"]);
});

test("theme toggle flips data-theme and persists it", async () => {
  const window = await mount(defaultFetch);
  assert.equal(window.document.documentElement.dataset.theme, "dark");
  window.document.querySelector("#theme-toggle").click();
  assert.equal(window.document.documentElement.dataset.theme, "light");
  assert.equal(window.localStorage.getItem("ledgerlens:theme"), "light");
});

test("copy button copies the full wallet address", async () => {
  const window = await mount(defaultFetch);
  window.document.querySelector(".copy-btn").click();
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(window.__copied, WALLET);
});

test("score lookup rejects a malformed wallet before calling the API", async () => {
  let fetchCalled = false;
  const window = await mount((...args) => {
    fetchCalled = true;
    return defaultFetch(...args);
  });
  window.document.querySelector("#wallet-input").value = "not-a-wallet";
  window.document.querySelector("#pair-input").value = PAIR;
  fetchCalled = false; // ignore the initial-load fetches
  window.document.querySelector("#lookup-btn").click();
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(fetchCalled, false);
  assert.match(
    window.document.querySelector("#lookup-error").textContent,
    /doesn't look like a Stellar wallet/,
  );
});

test("score lookup happy path renders the result and persists it", async () => {
  const window = await mount(defaultFetch);
  window.document.querySelector("#wallet-input").value = WALLET;
  window.document.querySelector("#pair-input").value = PAIR;
  window.document.querySelector("#lookup-btn").click();
  await new Promise((r) => setTimeout(r, 50));

  assert.equal(window.document.querySelector("#score-num").textContent, "91");
  assert.equal(window.document.querySelector("#score-risk-label").textContent, "High Risk");
  assert.ok(window.document.querySelector("#score-result").classList.contains("visible"));
  assert.deepEqual(JSON.parse(window.localStorage.getItem("ledgerlens:last-lookup")), {
    wallet: WALLET,
    pair: PAIR,
  });
});

test("score lookup surfaces the API's error detail on a 404", async () => {
  const window = await mount(defaultFetch);
  window.document.querySelector("#wallet-input").value = WALLET;
  window.document.querySelector("#pair-input").value = "XLM/FOO:" + "G" + "A".repeat(55);
  window.document.querySelector("#lookup-btn").click();
  await new Promise((r) => setTimeout(r, 50));
  assert.match(window.document.querySelector("#lookup-error").textContent, /Unknown asset pair/);
});
