/** Mirrors api.storage.ALERT_THRESHOLD — scores at or above this are flagged. */
export const ALERT_THRESHOLD = 50;

export function isFlagged(score: number): boolean {
  return score >= ALERT_THRESHOLD;
}

/**
 * Three-tier risk-score color banding for the rankings table (distinct
 * from `isFlagged`'s single ALERT_THRESHOLD cutoff used elsewhere): >=70
 * uses `flag` (genuinely high risk), 40-69 is `muted` (ambiguous, worth a
 * look but not alarming), <40 uses `up` (green — reads as "clear" the
 * same way a positive price move does). Only use this for the rankings
 * table's Risk Score column; other risk-score displays (ScoreBadge) use
 * the single-threshold flagged/not-flagged rule instead.
 */
export function riskScoreColorClass(score: number): string {
  if (score >= 70) return "text-flag";
  if (score >= 40) return "text-muted";
  return "text-up";
}

export function shortenWallet(wallet: string): string {
  if (wallet.length <= 12) return wallet;
  return `${wallet.slice(0, 4)}…${wallet.slice(-4)}`;
}

/** "XLM/USDC:GA5ZS...KZVN" -> "XLM/USDC" */
export function pairSymbol(pair: string): string {
  return pair.split(":")[0];
}

/** The issuer address after the ":" in a pair identifier, if any. */
export function pairIssuer(pair: string): string | null {
  const parts = pair.split(":");
  return parts.length > 1 ? parts[1] : null;
}

export function formatTimestamp(iso: string): string {
  return new Date(iso).toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

export function formatFeatureName(name: string): string {
  return name.replace(/_/g, " ");
}

export function formatPrice(price: number): string {
  const decimals = price < 1 ? 4 : 2;
  return `$${price.toFixed(decimals)}`;
}

export function formatPercent(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

export function formatVolume(volume: number): string {
  if (volume >= 1_000_000) return `$${(volume / 1_000_000).toFixed(2)}M`;
  if (volume >= 1_000) return `$${(volume / 1_000).toFixed(1)}K`;
  return `$${volume.toFixed(0)}`;
}
