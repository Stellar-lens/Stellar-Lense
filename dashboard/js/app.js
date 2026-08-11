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

async function checkHealth() {
  const dot = $("#status-dot");
  try {
    const data = await apiFetch("/health", { baseUrl: API_BASE });
    setStatusOnline(dot, data.status === "ok");
  } catch {
    setStatusOnline(dot, false);
  }
}

async function loadStats() {
  try {
    const [alerts, assets] = await Promise.all([
      apiFetch("/alerts/recent?limit=200", { baseUrl: API_BASE }),
      apiFetch("/assets/risk-ranking", { baseUrl: API_BASE }),
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
  } catch (e) {
    console.warn("Stats load failed:", e);
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

async function loadAlerts() {
  const tbody = $("#alerts-body");
  try {
    const data = await apiFetch("/alerts/recent?limit=50", { baseUrl: API_BASE });
    renderAlerts(tbody, data, ALERT_THRESHOLD);
  } catch (err) {
    renderAlertsError(tbody, err.message);
  }
}

async function loadAssets() {
  const grid = $("#asset-grid");
  try {
    const data = await apiFetch("/assets/risk-ranking", { baseUrl: API_BASE });
    renderAssets(grid, data);
  } catch (err) {
    renderAssetsError(grid, err.message);
  }
}

function refreshAll() {
  checkHealth();
  loadStats();
  loadAlerts();
  loadAssets();
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
