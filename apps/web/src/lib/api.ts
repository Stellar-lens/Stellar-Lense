/**
 * Typed client for apps/api. Field names and shapes mirror
 * apps/api/api/schemas.py exactly — see that file for the source of truth.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BenfordReport = {
  sample_size: number;
  chi_square: number;
  mad: number;
  /** Leading digit (1-9, as string keys once JSON round-trips) -> z-score. */
  z_scores: Record<string, number>;
  non_conforming: boolean;
};

export type RiskScore = {
  wallet: string;
  asset_pair: string;
  score: number;
  benford_flag: boolean;
  ml_flag: boolean;
  confidence: number;
  timestamp: string;
  features: Record<string, number>;
  benford: BenfordReport;
  /** Present only when the ML ensemble artifact is loaded; null on the
   * heuristic fallback path. See detection/model_inference.py. */
  shap: Record<string, number> | null;
};

export type Alert = {
  id: string;
  wallet: string;
  asset_pair: string;
  score: number;
  reason: string;
  timestamp: string;
};

export type AssetRiskRanking = {
  asset_pair: string;
  average_score: number;
  max_score: number;
  flagged_wallets: number;
  total_wallets: number;
};

export type ScoreHistoryPoint = {
  timestamp: string;
  average_score: number;
  max_score: number;
};

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${path} -> HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getRiskRanking(): Promise<AssetRiskRanking[]> {
  return apiFetch("/assets/risk-ranking");
}

export function getPairScores(pair: string): Promise<RiskScore[]> {
  return apiFetch(`/assets/${encodeURIComponent(pair)}/scores`);
}

export function getRecentAlerts(limit = 50): Promise<Alert[]> {
  return apiFetch(`/alerts/recent?limit=${limit}`);
}

export function getScoreHistory(pair: string): Promise<ScoreHistoryPoint[]> {
  return apiFetch(`/assets/${encodeURIComponent(pair)}/score-history`);
}
