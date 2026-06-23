use soroban_sdk::{contracttype, Address, BytesN, Symbol};

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum EmbargoExpiry {
    Indefinite,
    Until(u64),
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RiskScore {
    pub score: u32,
    pub benford_flag: bool,
    pub ml_flag: bool,
    pub timestamp: u64,
    pub confidence: u32,
    pub model_version: u32,
}

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

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AggregateRiskScore {
    pub aggregate_score: u32,
    pub pair_count: u32,
    pub max_pair_score: u32,
    pub max_pair: Symbol,
    pub benford_flag_count: u32,
    pub ml_flag_count: u32,
    pub last_updated: u64,
    pub decay_lambda_applied: bool,
}

/// Standard single-key ECDSA attestation over a score payload.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScoreAttestation {
    pub commitment: BytesN<32>,
    pub signature: BytesN<65>,
}

/// Threshold-signature attestation: t-of-n signers produce one 65-byte proof.
/// See `docs/threshold-attestation-spec.md`.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ThresholdAttestation {
    pub commitment: BytesN<32>,
    pub threshold_sig: BytesN<65>,
    pub participating_signers: soroban_sdk::Vec<Address>,
}

/// Unified attestation input for `submit_score`.
/// Wraps both attestation variants so the function stays within
/// Soroban's 10-parameter limit.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ScoreAttestationInput {
    Single(ScoreAttestation),
    Threshold(ThresholdAttestation),
}

/// Decay-adjusted view of a score, returned by `get_effective_score`.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EffectiveRiskScore {
    pub raw_score: u32,
    pub effective_score: u32,
    pub decay_applied: bool,
    pub elapsed_secs: u64,
    pub timestamp: u64,
    pub confidence: u32,
    pub model_version: u32,
    pub benford_flag: bool,
    pub ml_flag: bool,
}

/// Per-model-version aggregate stats, returned by `get_model_version_stats`.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelVersionStats {
    pub model_version: u32,
    pub submission_count: u32,
    pub score_sum: u64,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelSubmission {
    pub model_version: u32,
    pub score: u32,
    pub confidence: u32,
    pub benford_flag: bool,
    pub ml_flag: bool,
    pub attestation: ScoreAttestation,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BatchEntryResult {
    pub index: u32,
    pub accepted: bool,
    pub rejection_code: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BatchResult {
    pub accepted_count: u32,
    pub rejected_count: u32,
    pub results: soroban_sdk::Vec<BatchEntryResult>,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BatchAttestation {
    pub merkle_root: BytesN<32>,
    pub signature: BytesN<65>,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScoreSubmissionWithProof {
    pub submission: ScoreSubmission,
    pub proof: soroban_sdk::Vec<BytesN<32>>,
    pub proof_flags: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeProposal {
    pub new_wasm_hash: BytesN<32>,
    pub proposed_at: u64,
    pub executable_after: u64,
    pub proposed_by: Address,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScoreTrend {
    pub trend: i32,
    pub consecutive: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScoreFloorPolicy {
    pub enabled: bool,
    pub high_water_mark: u32,
    pub floor_value: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SnapshotRecord {
    pub root: BytesN<32>,
    pub leaf_count: u64,
    pub committed_at: u64,
    pub committed_by: Address,
}

#[contracttype]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub struct TierBounds {
    pub min_score: u32,
    pub max_score: u32,
}

#[contracttype]
#[derive(Clone)]
pub enum DataKey {
    Admin,
    Service,
    Score(Address, Symbol),
    Paused,
    PendingAdmin,
    Watchlist(Address),
    RiskThreshold,
    JumpThreshold,
    ScoreHistory(Address, Symbol),
    ContractVersion,
    AssetPairs(Address),
    PairWeight(Symbol),
    AggregateScore(Address),
    PendingUpgrade,
    UpgradeDelay,
    ServiceSet,
    ServiceThreshold,
    StalenessWindow,
    LastSubmitTime(Address, Symbol),
    CooldownSecs,
    ScoreCount(Address, Symbol),
    ServicePubKey,
    /// Aggregate secp256k1 pubkey for the t-of-n threshold signing group.
    AggregatePubKey,
    SignerTier(Address),
    HistoryMaxDepth,
    DecayRateNumerator,
    DecayRateDenominator,
    FeeToken,
    WithdrawalLock,
    PairPaused(Symbol),
    PausedPairIndex,
    AdminSet,
    AdminThreshold,
    ScoreDelegate(Address),
    TrendState(Address, Symbol),
    Counterparties(Address, Symbol),
    ScoreFloorHighWaterMark,
    ScoreFloorMinValue,
    ScoreFloorEnabled,
    HistoricalMaxScore(Address, Symbol),
    HysteresisMargin,
    RiskBandState(Address, Symbol),
    ScoreEmbargo(Address),
    ConsensusThresholdK,
    ConsensusEpsilon,
    GlobalMinConfidence,
    /// Per-(wallet,pair) consecutive breach count for escalation.
    BreachCount(Address, Symbol),
    /// Admin-configured escalation threshold (N consecutive breaches).
    EscalationThreshold,
    /// Per-model-version stats: submission count + score sum.
    ModelStats(u32),
    /// Sorted list of model versions seen.
    ModelVersionList,
}
