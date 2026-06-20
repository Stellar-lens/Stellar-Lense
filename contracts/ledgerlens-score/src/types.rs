use soroban_sdk::{contracttype, Address};

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DataKey {
    Admin,
    Service,
    Config,
    SignerTier(Address),
}

#[contracttype]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub struct TierBounds {
    pub min_score: u32,
    pub max_score: u32,
}
