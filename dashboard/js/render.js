import { pill, formatTs, scoreClass, scoreLabel, shortenWallet } from "./formatters.js";

export function setStatusOnline(dot, online) {
  dot.classList.toggle("offline", !online);
}

export function renderStats({ flaggedEl, assetsEl, avgEl }, alerts, assets, alertThreshold) {
  const flagged = alerts.filter((a) => a.score >= alertThreshold).length;
  const avgScore = assets.length
    ? Math.round(assets.reduce((s, a) => s + a.average_score, 0) / assets.length)
    : "—";
  for (const el of [flaggedEl, assetsEl, avgEl]) el.classList.remove("skeleton");
  flaggedEl.textContent = flagged;
  assetsEl.textContent = assets.length;
  avgEl.textContent = avgScore;
}

export function renderScoreResult(refs, data) {
  refs.gauge.className = `gauge ${scoreClass(data.score)}`;
  refs.scoreNum.textContent = data.score;
  refs.riskLabel.textContent = scoreLabel(data.score);

  refs.flagRow.innerHTML = "";
  if (data.benford_flag)
    refs.flagRow.innerHTML += `<span class="badge benford">Benford anomaly</span>`;
  if (data.ml_flag) refs.flagRow.innerHTML += `<span class="badge ml">ML flagged</span>`;
  if (!data.benford_flag && !data.ml_flag)
    refs.flagRow.innerHTML += `<span class="badge clean">Clean signals</span>`;

  refs.meta.textContent = `Confidence ${Math.round(data.confidence)}% · Last updated ${formatTs(data.timestamp)}`;
}

export function renderAlerts(tbody, alerts, alertThreshold) {
  const flagged = alerts.filter((a) => a.score >= alertThreshold);
  if (!flagged.length) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state">No wallets currently flagged</div></td></tr>`;
    return;
  }
  tbody.innerHTML = flagged
    .map(
      (a) => `
        <tr>
          <td title="${a.wallet}">
            <span class="wallet-cell">${shortenWallet(a.wallet)}</span>
            <button class="copy-btn" data-wallet="${a.wallet}" title="Copy wallet address" aria-label="Copy wallet address">⧉</button>
          </td>
          <td>${a.asset_pair}</td>
          <td>${pill(a.score)}</td>
          <td>${a.reason}</td>
          <td>${formatTs(a.timestamp)}</td>
        </tr>`,
    )
    .join("");
}

export function renderAlertsError(tbody, message) {
  tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state">Failed to load alerts: ${message}</div></td></tr>`;
}

export function renderAssets(grid, assets) {
  if (!assets.length) {
    grid.innerHTML = `<div class="empty-state">No asset data yet</div>`;
    return;
  }
  grid.innerHTML = assets
    .map(
      (a) => `
        <div class="asset-card">
          <div class="asset-code">${a.asset_pair}</div>
          <div class="asset-avg" style="color:var(--${scoreClass(Math.round(a.average_score))})">${Math.round(a.average_score)}</div>
          <div class="asset-meta">
            Max ${a.max_score} · ${a.flagged_wallets}/${a.total_wallets} flagged
          </div>
        </div>`,
    )
    .join("");
}

export function renderAssetsError(grid, message) {
  grid.innerHTML = `<div class="empty-state">Failed to load assets: ${message}</div>`;
}
