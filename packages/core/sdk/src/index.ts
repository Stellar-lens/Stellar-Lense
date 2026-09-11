/**
 * @stellar-lense/sdk — TypeScript SDK for the StellarLense API
 *
 * Features:
 * - Full TypeScript type inference for all API responses
 * - Zod runtime validation (unknown fields stripped)
 * - Browser + Node.js (ESM + CJS dual build)
 * - Timeout and error handling
 *
 * @example
 * ```ts
 * import { StellarLenseClient } from "@stellar-lense/sdk";
 *
 * const client = new StellarLenseClient({ baseUrl: "http://localhost:8000" });
 * const health = await client.getHealth();
 * console.log(health);
 * ```
 */

/**
 * {@link StellarLenseClient} is the HTTP client; {@link StellarLenseError} is the
 * error type every client method rejects with.
 */
export { StellarLenseClient, StellarLenseError } from "./client";
/** Constructor options for {@link StellarLenseClient}. */
export type { StellarLenseClientOptions } from "./client";

/**
 * Zod schemas backing every API response. Exported so consumers can run their
 * own validation, derive partial schemas, or reuse them in tests. Each
 * `XxxSchema` parses the payload described by the matching `Xxx` type below.
 */
export {
  // Schemas (for custom validation)
  StellarAddressSchema,
  RiskScoreSchema,
  AlertSchema,
  AlertTypeSchema,
  LiquidityPoolTradeSchema,
  AssetRiskRankingSchema,
  RingSchema,
  PairCorrelationSchema,
  CounterfactualSchema,
  WebhookSubscriberSchema,
  HealthSchema,
  PaginatedScoresSchema,
  ApiErrorSchema,
} from "./schemas";

/**
 * Static types inferred from the Zod schemas above, describing the shape of
 * each parsed API response.
 */
export type {
  RiskScore,
  Alert,
  AlertType,
  LiquidityPoolTrade,
  AssetRiskRanking,
  Ring,
  PairCorrelation,
  Counterfactual,
  WebhookSubscriber,
  Health,
  PaginatedScores,
  ApiError,
} from "./schemas";
