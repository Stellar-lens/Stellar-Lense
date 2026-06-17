// Ledger TTL constants assume ~5 s per ledger on Stellar mainnet.
pub const SCORE_TTL_THRESHOLD: u32 = 518_400; // ~30 days
pub const SCORE_TTL_EXTEND_TO: u32 = 777_600; // ~45 days

/// Maximum score-history entries retained per wallet/asset-pair ring buffer.
pub const HISTORY_MAX_DEPTH: u32 = 10;

/// Maximum number of entries accepted in a single batch submission call.
pub const MAX_BATCH_SIZE: u32 = 20;

/// Default risk threshold used when no threshold has been configured by admin.
pub const DEFAULT_RISK_THRESHOLD: u32 = 75;

/// Semantic contract version; bump on breaking ABI changes.
pub const CONTRACT_VERSION: u32 = 1;

/// Practical upper bound on the number of distinct asset pairs tracked per
/// wallet. `get_aggregate_score` iterates the wallet's full `AssetPairs`
/// list, so its cost is O(N) in this value; it is not enforced on-chain,
/// but documents the assumption the aggregate engine is designed around.
/// See the rustdoc on `get_aggregate_score` for detail.
pub const MAX_WALLET_PAIRS: u32 = 20;
