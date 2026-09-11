/**
 * Placeholder price/24h-change/volume for the rankings table. apps/api has
 * no market-data endpoint (its schemas only cover risk scores/alerts — see
 * api/schemas.py) — the design spec calls for Price/24h/Volume columns
 * regardless, so these are synthesized. Seeded deterministically from the
 * asset pair string (not Math.random()) so the same row shows the same
 * numbers on every request instead of reshuffling on reload.
 */

export type MarketData = {
  price: number;
  change24h: number;
  volume: number;
};

function hashSeed(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// mulberry32 — small, deterministic, good enough for placeholder data.
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const STABLE_CODES = new Set(["USDC", "USDT", "EURC"]);

export function getPlaceholderMarketData(assetPair: string): MarketData {
  // Price is the base asset's price in USD terms — check the base code
  // (before "/"), not the counter, against the stablecoin set.
  const baseCode = assetPair.split("/")[0];
  const rand = mulberry32(hashSeed(assetPair));

  if (STABLE_CODES.has(baseCode)) {
    return {
      price: 0.995 + rand() * 0.01,
      change24h: (rand() - 0.5) * 0.4,
      volume: 500_000 + rand() * 4_500_000,
    };
  }

  return {
    price: 0.01 + rand() * 2,
    change24h: (rand() - 0.5) * 30,
    volume: 20_000 + rand() * 1_500_000,
  };
}
