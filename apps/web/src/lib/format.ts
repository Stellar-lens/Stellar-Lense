/** Mirrors api.storage.ALERT_THRESHOLD — scores at or above this are flagged. */
export const ALERT_THRESHOLD = 50;

export function isFlagged(score: number): boolean {
  return score >= ALERT_THRESHOLD;
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
