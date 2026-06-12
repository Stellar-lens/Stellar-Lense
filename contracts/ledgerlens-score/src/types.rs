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
}
