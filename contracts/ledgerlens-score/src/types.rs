use soroban_sdk::{contracttype, Address, Symbol};

/// On-chain record of the latest LedgerLens risk assessment for a
/// wallet / asset-pair combination. Written by `submit_score` and
/// read by `get_score`.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RiskScore {
    /// Overall risk score, 0-100. Higher = more suspicious.
    pub score: u32,
    /// True if the Benford's Law engine flagged this entity.
    pub benford_flag: bool,
    /// True if the ML ensemble classifier flagged this entity.
    pub ml_flag: bool,
    /// Ledger timestamp when this score was computed off-chain.
    pub timestamp: u64,
    /// Model confidence for this score, 0-100.
    pub confidence: u32,
    /// Integer version of the detection-pipeline model that produced
    /// this score.  Allows consumers to detect stale scores when the
    /// pipeline is retrained.
    pub model_version: u32,
}

/// A single entry in a batch score submission.  Mirrors the fields of
/// `submit_score` so the service can write many scores in one call.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScoreSubmission {
    pub wallet: Address,
    pub asset_pair: Symbol,
    pub score: u32,
    pub benford_flag: bool,
    pub ml_flag: bool,
    pub timestamp: u64,
    pub confidence: u32,
    pub model_version: u32,
}

/// Cross-asset aggregate risk view for a single wallet — a weighted
/// average of every per-pair `RiskScore` the wallet currently has.
/// Returned by `get_aggregate_score`; see that function's rustdoc for the
/// exact formula and complexity bound.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AggregateRiskScore {
    /// Weighted average of all contributing per-pair scores, 0-100.
    pub aggregate_score: u32,
    /// Number of distinct asset pairs the wallet has a score for.
    pub pair_count: u32,
    /// The highest individual per-pair score across all of the wallet's pairs.
    pub max_pair_score: u32,
    /// The asset pair that produced `max_pair_score`.
    pub max_pair: Symbol,
    /// Count of the wallet's pairs with `benford_flag == true`.
    pub benford_flag_count: u32,
    /// Count of the wallet's pairs with `ml_flag == true`.
    pub ml_flag_count: u32,
    /// Ledger timestamp of the most recently updated component score.
    pub last_updated: u64,
}

#[contracttype]
#[derive(Clone)]
pub enum DataKey {
    /// Address allowed to call admin-only functions.
    Admin,
    /// Address of the authorised LedgerLens off-chain scoring service.
    Service,
    /// Latest risk score for a (wallet, asset_pair) pair.
    Score(Address, Symbol),
    /// Boolean flag — true when the contract is paused.
    Paused,
    /// Pending new admin address during a two-step admin transfer.
    PendingAdmin,
    /// Per-wallet watchlist flag (true = high-priority monitoring).
    Watchlist(Address),
    /// Global risk-score threshold; scores ≥ threshold emit a breach event.
    RiskThreshold,
    /// Ordered ring buffer of the last N risk scores for a wallet/pair.
    ScoreHistory(Address, Symbol),
    /// Baked-in contract version number.
    ContractVersion,
    /// Ordered, de-duplicated list of asset pairs a wallet has a score for.
    AssetPairs(Address),
    /// Per-asset-pair weight used by the aggregate risk computation.
    /// Defaults to 1 (simple average) when unset.
    PairWeight(Symbol),
    /// Cached snapshot of the most recently computed aggregate risk score
    /// for a wallet, refreshed as a side effect of `submit_score` /
    /// `submit_scores_batch`. `get_aggregate_score` never reads this cache —
    /// it always recomputes from the live per-pair scores — so this key
    /// exists purely as a cheap snapshot for off-chain indexers.
    AggregateScore(Address),
    /// Ordered set of N addresses authorised to co-sign score submissions.
    /// A score submission is accepted only when M of these addresses have
    /// individually authorized it in the same transaction.
    ServiceSet,
    /// The M-of-N threshold: the minimum number of service-set members that
    /// must sign a `submit_score` call for it to be accepted.
    ServiceThreshold,
}
