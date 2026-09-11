export function scoreClass(score) {
  if (score < 40) return "low";
  if (score < 70) return "medium";
  return "high";
}

export function scoreLabel(score) {
  if (score < 40) return "Low Risk";
  if (score < 70) return "Medium Risk";
  return "High Risk";
}

export function pill(score) {
  const cls = scoreClass(score);
  return `<span class="score-pill ${cls}">${score}</span>`;
}

export function formatTs(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortenWallet(wallet) {
  return `${wallet.slice(0, 12)}…${wallet.slice(-4)}`;
}
