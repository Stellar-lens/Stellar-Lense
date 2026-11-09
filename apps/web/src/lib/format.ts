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

export type PairAsset = { code: string; issuer: string | null };

/** "XLM/USDC:GA5Z…" -> [{XLM, null}, {USDC, "GA5Z…"}]. Each side of a pair
 * id is "XLM" or "CODE:ISSUER"; issuers never contain "/". */
export function pairAssets(pair: string): [PairAsset, PairAsset] {
  const [base, counter] = pair.split("/");
  const parse = (side: string = ""): PairAsset => {
    const [code, issuer] = side.split(":");
    return { code, issuer: issuer ?? null };
  };
  return [parse(base), parse(counter)];
}

/** "yUSDC:GDGT…/USDC:GA5Z…" -> "yUSDC/USDC" */
export function pairSymbol(pair: string): string {
  const [base, counter] = pairAssets(pair);
  return `${base.code}/${counter.code}`;
}

/** Issuers of the pair's credit assets, e.g. ["GA5Z…"] for XLM/USDC. */
export function pairIssuers(pair: string): string[] {
  return pairAssets(pair)
    .map((a) => a.issuer)
    .filter((i): i is string => i !== null);
}

export function formatTimestamp(iso: string): string {
  return new Date(iso).toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

export function formatFeatureName(name: string): string {
  return name.replace(/_/g, " ");
}

/** Price in counter-asset units, e.g. "0.1003 USDC". */
export function formatPrice(price: number, unit: string): string {
  const decimals = price < 1 ? 4 : price < 1000 ? 2 : 0;
  return `${price.toFixed(decimals)} ${unit}`;
}

export function formatPercent(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

/** Compact amount in the given asset's units, e.g. "4.81M USDC". */
export function formatVolume(volume: number, unit: string): string {
  if (volume >= 1_000_000) return `${(volume / 1_000_000).toFixed(2)}M ${unit}`;
  if (volume >= 1_000) return `${(volume / 1_000).toFixed(1)}K ${unit}`;
  return `${volume.toFixed(0)} ${unit}`;
}
