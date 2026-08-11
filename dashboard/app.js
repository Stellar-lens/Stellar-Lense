(() => {
  "use strict";

  const API_BASE = window.LEDGERLENS_API || "http://localhost:8000";
  const ALERT_THRESHOLD = 75;

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const $ = (sel) => document.querySelector(sel);

  function scoreClass(score) {
    if (score < 40) return "low";
    if (score < 70) return "medium";
    return "high";
  }

  function scoreLabel(score) {
    if (score < 40) return "Low Risk";
    if (score < 70) return "Medium Risk";
    return "High Risk";
  }

  function pill(score) {
    const cls = scoreClass(score);
    return `<span class="score-pill ${cls}">${score}</span>`;
  }

  function formatTs(iso) {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  }

  async function apiFetch(path) {
    const resp = await fetch(`${API_BASE}${path}`);
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const body = await resp.json();
        if (body?.detail) detail = body.detail;
      } catch {
        // response wasn't JSON — fall back to statusText
      }
      throw new Error(detail);
    }
    return resp.json();
  }

  // ── Health check ─────────────────────────────────────────────────────────────

  async function checkHealth() {
    const dot = $("#status-dot");
    try {
      const data = await apiFetch("/health");
      dot.classList.toggle("offline", data.status !== "ok");
    } catch {
      dot.classList.add("offline");
    }
  }

  // ── Stats row ─────────────────────────────────────────────────────────────────

  async function loadStats() {
    try {
      const [alerts, assets] = await Promise.all([
        apiFetch("/alerts/recent?limit=200"),
        apiFetch("/assets/risk-ranking"),
      ]);
      const flagged = alerts.filter((a) => a.score >= ALERT_THRESHOLD).length;
      const avgScore = assets.length
        ? Math.round(assets.reduce((s, a) => s + a.average_score, 0) / assets.length)
        : "—";

      $("#stat-flagged").textContent = flagged;
      $("#stat-assets").textContent = assets.length;
      $("#stat-avg").textContent = avgScore;
    } catch (e) {
      console.warn("Stats load failed:", e);
    }
  }

  // ── Score lookup ──────────────────────────────────────────────────────────────

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

    const btn = $("#lookup-btn");
    btn.disabled = true;
    btn.textContent = "Scoring…";

    try {
      // encodeURI (not encodeURIComponent) — the API's pair path segment
      // is itself slash-delimited (e.g. XLM/USDC:GISSUER...) and must
      // reach the server with literal "/" characters intact.
      const data = await apiFetch(`/score/${wallet}/${encodeURI(pair)}`);

      const gauge = $("#score-gauge");
      gauge.className = `gauge ${scoreClass(data.score)}`;
      $("#score-num").textContent = data.score;
      $("#score-risk-label").textContent = scoreLabel(data.score);

      const flagRow = $("#flag-row");
      flagRow.innerHTML = "";
      if (data.benford_flag) flagRow.innerHTML += `<span class="badge benford">Benford anomaly</span>`;
      if (data.ml_flag) flagRow.innerHTML += `<span class="badge ml">ML flagged</span>`;
      if (!data.benford_flag && !data.ml_flag) flagRow.innerHTML += `<span class="badge clean">Clean signals</span>`;

      $("#score-meta").textContent =
        `Confidence ${Math.round(data.confidence)}% · Last updated ${formatTs(data.timestamp)}`;

      resultEl.classList.add("visible");
    } catch (err) {
      errEl.textContent = `Scoring failed: ${err.message}`;
      errEl.style.display = "block";
    } finally {
      btn.disabled = false;
      btn.textContent = "Score";
    }
  }

  // ── Alerts table ──────────────────────────────────────────────────────────────

  async function loadAlerts() {
    const tbody = $("#alerts-body");
    try {
      const data = await apiFetch("/alerts/recent?limit=50");
      const flagged = data.filter((a) => a.score >= ALERT_THRESHOLD);
      if (!flagged.length) {
        tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state">No wallets currently flagged</div></td></tr>`;
        return;
      }
      tbody.innerHTML = flagged.map((a) => `
        <tr>
          <td title="${a.wallet}">${a.wallet.slice(0, 12)}…${a.wallet.slice(-4)}</td>
          <td>${a.asset_pair}</td>
          <td>${pill(a.score)}</td>
          <td>${a.reason}</td>
          <td>${formatTs(a.timestamp)}</td>
        </tr>`).join("");
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state">Failed to load alerts: ${err.message}</div></td></tr>`;
    }
  }

  // ── Asset ranking ─────────────────────────────────────────────────────────────

  async function loadAssets() {
    const grid = $("#asset-grid");
    try {
      const data = await apiFetch("/assets/risk-ranking");
      if (!data.length) {
        grid.innerHTML = `<div class="empty-state">No asset data yet</div>`;
        return;
      }
      grid.innerHTML = data.map((a) => `
        <div class="asset-card">
          <div class="asset-code">${a.asset_pair}</div>
          <div class="asset-avg" style="color:var(--${scoreClass(Math.round(a.average_score))})">${Math.round(a.average_score)}</div>
          <div class="asset-meta">
            Max ${a.max_score} · ${a.flagged_wallets}/${a.total_wallets} flagged
          </div>
        </div>`).join("");
    } catch (err) {
      grid.innerHTML = `<div class="empty-state">Failed to load assets: ${err.message}</div>`;
    }
  }

  // ── Boot ──────────────────────────────────────────────────────────────────────

  function init() {
    checkHealth();
    loadStats();
    loadAlerts();
    loadAssets();

    $("#lookup-btn").addEventListener("click", lookupScore);
    $("#wallet-input").addEventListener("keydown", (e) => { if (e.key === "Enter") lookupScore(); });
    $("#pair-input").addEventListener("keydown", (e) => { if (e.key === "Enter") lookupScore(); });

    // Refresh every 60s
    setInterval(() => {
      checkHealth();
      loadStats();
      loadAlerts();
      loadAssets();
    }, 60_000);
  }

  document.readyState === "loading"
    ? document.addEventListener("DOMContentLoaded", init)
    : init();
})();
