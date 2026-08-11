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
const LAST_LOOKUP_KEY = "ledgerlens:last-lookup";

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
    localStorage.setItem(LAST_LOOKUP_KEY, JSON.stringify({ wallet, pair }));
  } catch (err) {
    errEl.textContent = `Scoring failed: ${err.message}`;
    errEl.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Score";
  }
}

const alertsState = { data: [], filter: "", sortKey: "score", sortDir: "desc" };

function renderAlertsView() {
  const term = alertsState.filter.toLowerCase();
  const filtered = term
    ? alertsState.data.filter(
        (a) => a.wallet.toLowerCase().includes(term) || a.asset_pair.toLowerCase().includes(term),
      )
    : alertsState.data;

  const { sortKey, sortDir } = alertsState;
  const sorted = [...filtered].sort((a, b) => {
    const cmp =
      sortKey === "timestamp" ? a.timestamp.localeCompare(b.timestamp) : a.score - b.score;
    return sortDir === "asc" ? cmp : -cmp;
  });

  renderAlerts($("#alerts-body"), sorted, ALERT_THRESHOLD);
}

async function loadAlerts(signal) {
  try {
    alertsState.data = await apiFetch("/alerts/recent?limit=50", { baseUrl: API_BASE, signal });
    renderAlertsView();
  } catch (err) {
    if (isAbort(err)) return;
    renderAlertsError($("#alerts-body"), err.message);
  }
}

const assetsState = { data: [], filter: "" };

function renderAssetsView() {
  const term = assetsState.filter.toLowerCase();
  const filtered = term
    ? assetsState.data.filter((a) => a.asset_pair.toLowerCase().includes(term))
    : assetsState.data;
  renderAssets($("#asset-grid"), filtered);
}

async function loadAssets(signal) {
  try {
    assetsState.data = await apiFetch("/assets/risk-ranking", { baseUrl: API_BASE, signal });
    renderAssetsView();
  } catch (err) {
    if (isAbort(err)) return;
    renderAssetsError($("#asset-grid"), err.message);
  }
}

// Aborts the previous cycle's still-in-flight requests before starting a new
// one, so a slow response can't land after a newer refresh already has.
let refreshController = null;

async function refreshAll() {
  refreshController?.abort();
  refreshController = new AbortController();
  const { signal } = refreshController;

  await Promise.allSettled([
    checkHealth(signal),
    loadStats(signal),
    loadAlerts(signal),
    loadAssets(signal),
  ]);
  if (signal.aborted) return;
  $("#last-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

function restoreLastLookup() {
  try {
    const saved = JSON.parse(localStorage.getItem(LAST_LOOKUP_KEY));
    if (saved?.wallet) $("#wallet-input").value = saved.wallet;
    if (saved?.pair) $("#pair-input").value = saved.pair;
  } catch {
    // corrupt or absent — ignore, inputs stay empty
  }
}

function init() {
  restoreLastLookup();
  refreshAll();

  $("#refresh-btn").addEventListener("click", refreshAll);
  $("#lookup-btn").addEventListener("click", lookupScore);
  $("#wallet-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") lookupScore();
  });
  $("#pair-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") lookupScore();
  });

  $("#alerts-filter").addEventListener("input", (e) => {
    alertsState.filter = e.target.value.trim();
    renderAlertsView();
  });

  $("#alerts-body").addEventListener("click", (e) => {
    const btn = e.target.closest(".copy-btn");
    if (!btn) return;
    navigator.clipboard.writeText(btn.dataset.wallet).then(() => {
      const original = btn.textContent;
      btn.textContent = "✓";
      setTimeout(() => {
        btn.textContent = original;
      }, 1000);
    });
  });

  $("#assets-filter").addEventListener("input", (e) => {
    assetsState.filter = e.target.value.trim();
    renderAssetsView();
  });

  document.querySelectorAll(".alerts-table th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sortKey;
      if (alertsState.sortKey === key) {
        alertsState.sortDir = alertsState.sortDir === "asc" ? "desc" : "asc";
      } else {
        alertsState.sortKey = key;
        alertsState.sortDir = "desc";
      }
      document
        .querySelectorAll(".alerts-table th.sortable")
        .forEach((h) => h.classList.remove("sort-asc", "sort-desc"));
      th.classList.add(alertsState.sortDir === "asc" ? "sort-asc" : "sort-desc");
      renderAlertsView();
    });
  });

  setInterval(refreshAll, REFRESH_INTERVAL_MS);
}

document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
