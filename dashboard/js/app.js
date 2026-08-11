import { apiFetch, apiFetchWithRetry } from "./api.js";
import {
  ALERT_THRESHOLD,
  DEFAULT_API_BASE,
  PAIR_PATTERN,
  REFRESH_INTERVAL_MS,
  WALLET_PATTERN,
} from "./constants.js";
import {
  renderAlerts,
  renderAlertsError,
  renderAssets,
  renderAssetsError,
  renderScoreResult,
  renderStats,
  setStatusOnline,
} from "./render.js";

const API_BASE = window.LEDGERLENS_API || DEFAULT_API_BASE;

const $ = (sel) => document.querySelector(sel);

function isAbort(err) {
  return err?.name === "AbortError";
}

async function checkHealth(signal) {
  const dot = $("#status-dot");
  try {
    const data = await apiFetch("/health", { baseUrl: API_BASE, signal });
    setStatusOnline(dot, data.status === "ok");
  } catch (err) {
    if (isAbort(err)) return;
    setStatusOnline(dot, false);
  }
}

async function loadStats(signal) {
  try {
    const [alerts, assets] = await Promise.all([
      apiFetch("/alerts/recent?limit=200", { baseUrl: API_BASE, signal }),
      apiFetch("/assets/risk-ranking", { baseUrl: API_BASE, signal }),
    ]);
    renderStats(
      {
        flaggedEl: $("#stat-flagged"),
        assetsEl: $("#stat-assets"),
        avgEl: $("#stat-avg"),
      },
      alerts,
      assets,
      ALERT_THRESHOLD,
    );
  } catch (err) {
    if (isAbort(err)) return;
    console.warn("Stats load failed:", err);
  }
}

async function lookupScore() {
  const wallet = $("#wallet-input").value.trim();
  const pair = $("#pair-input").value.trim();
  const errEl = $("#lookup-error");
  const resultEl = $("#score-result");

  errEl.style.display = "none";
  resultEl.classList.remove("visible");

  if (!wallet || !pair) {
    errEl.textContent = "Please enter both wallet address and asset pair.";
    errEl.style.display = "block";
    return;
  }
  if (!WALLET_PATTERN.test(wallet)) {
    errEl.textContent =
      "That doesn't look like a Stellar wallet address (should start with G, 56 characters).";
    errEl.style.display = "block";
    return;
  }
  if (!PAIR_PATTERN.test(pair)) {
    errEl.textContent =
      "That doesn't look like a valid asset pair (expected e.g. XLM/USDC:GISSUER...).";
    errEl.style.display = "block";
    return;
  }

  const btn = $("#lookup-btn");
  btn.disabled = true;
  btn.textContent = "Scoring…";

  try {
    // encodeURI (not encodeURIComponent) — the pair path segment is itself
    // slash-delimited (e.g. XLM/USDC:GISSUER...) and must reach the server
    // with literal "/" characters intact.
    const data = await apiFetchWithRetry(`/score/${wallet}/${encodeURI(pair)}`, {
      baseUrl: API_BASE,
    });

    renderScoreResult(
      {
        gauge: $("#score-gauge"),
        scoreNum: $("#score-num"),
        riskLabel: $("#score-risk-label"),
        flagRow: $("#flag-row"),
        meta: $("#score-meta"),
      },
      data,
    );

    resultEl.classList.add("visible");
  } catch (err) {
    errEl.textContent = `Scoring failed: ${err.message}`;
    errEl.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Score";
  }
}

async function loadAlerts(signal) {
  const tbody = $("#alerts-body");
  try {
    const data = await apiFetch("/alerts/recent?limit=50", { baseUrl: API_BASE, signal });
    renderAlerts(tbody, data, ALERT_THRESHOLD);
  } catch (err) {
    if (isAbort(err)) return;
    renderAlertsError(tbody, err.message);
  }
}

async function loadAssets(signal) {
  const grid = $("#asset-grid");
  try {
    const data = await apiFetch("/assets/risk-ranking", { baseUrl: API_BASE, signal });
    renderAssets(grid, data);
  } catch (err) {
    if (isAbort(err)) return;
    renderAssetsError(grid, err.message);
  }
}

// Aborts the previous cycle's still-in-flight requests before starting a new
// one, so a slow response can't land after a newer refresh already has.
let refreshController = null;

function refreshAll() {
  refreshController?.abort();
  refreshController = new AbortController();
  const { signal } = refreshController;

  checkHealth(signal);
  loadStats(signal);
  loadAlerts(signal);
  loadAssets(signal);
}

function init() {
  refreshAll();

  $("#lookup-btn").addEventListener("click", lookupScore);
  $("#wallet-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") lookupScore();
  });
  $("#pair-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") lookupScore();
  });

  setInterval(refreshAll, REFRESH_INTERVAL_MS);
}

document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
