/**
 * Typed client for apps/api. Field names and shapes mirror
 * apps/api/api/schemas.py exactly — see that file for the source of truth.
 */

// All API calls run server-side (React Server Components), so a runtime
// API_URL (e.g. http://api:8000 inside docker compose) takes precedence over
// the build-time NEXT_PUBLIC_API_URL.
const API_BASE =
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BenfordReport = {
  sample_size: number;
  chi_square: number;
  chi_square_pvalue: number;
  mad: number;
  /** Leading digit (1-9, as string keys once JSON round-trips) -> z-score. */
  z_scores: Record<string, number>;
  /** False when there were too few trades for a first-digit test to mean anything. */
  sufficient_sample: boolean;
  non_conforming: boolean;
};

export type ModelInfo = {
  model_id: string;
  trained_on: string;
};

export type RiskScore = {
  wallet: string;
  asset_pair: string;
  score: number;
  /** How the score was produced: fixed heuristic weights, or a trained model. */
  method: "heuristic" | "ml";
  /** Which model, and what it was trained on; null for heuristic scores. */
  model: ModelInfo | null;
  benford_flag: boolean;
  ml_flag: boolean;
  confidence: number;
  trade_count: number;
  timestamp: string;
  features: Record<string, number>;
  benford: BenfordReport;
  /** SHAP attributions; present only for method === "ml". */
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

export type Meta = {
  /** "live": Stellar network data from the pipeline. "demo": synthetic seed data. */
  mode: "live" | "demo";
  network: string | null;
  /** Close time of the newest trade behind the current scores. */
  data_as_of: string | null;
  scored_at: string | null;
  last_ingest: string | null;
  pairs_tracked: number;
  scoring: {
    method: "heuristic" | "ml";
    model: ModelInfo | null;
    min_trades: number;
    window_start: string | null;
    window_end: string | null;
  };
  notice: string | null;
};

export type MarketData = {
  asset_pair: string;
  /** Counter-asset units per one base unit; null if no trades in 24h. */
  price: number | null;
  change_24h_pct: number | null;
  base_volume_24h: number;
  counter_volume_24h: number;
  trade_count_24h: number;
  window_start: string;
  window_end: string;
  fetched_at: string;
};

export class ApiError extends Error {
  constructor(
    readonly path: string,
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${path} -> HTTP ${status}: ${detail}`);
  }
}

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(path, res.status, detail);
  }
  return res.json() as Promise<T>;
}

export function getMeta(): Promise<Meta> {
  return apiFetch("/meta");
}

export function getMarket(): Promise<MarketData[]> {
  return apiFetch("/market");
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
