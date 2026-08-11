export const DEFAULT_API_BASE = "http://localhost:8000";
export const ALERT_THRESHOLD = 75;
export const REFRESH_INTERVAL_MS = 60_000;

// Stellar public key: 'G' + 55 base32 characters.
export const WALLET_PATTERN = /^G[A-Z2-7]{55}$/;

// Asset pair identifier, e.g. "XLM/USDC:GA5Z..." — each side is an asset
// code, optionally suffixed with ":<issuer public key>" for non-native assets.
export const PAIR_PATTERN = /^\w{1,12}(:G[A-Z2-7]{55})?\/\w{1,12}(:G[A-Z2-7]{55})?$/;
