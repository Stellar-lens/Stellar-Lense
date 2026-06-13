//! LedgerLens on-chain risk score registry.
//!
//! Stores the most recent LedgerLens Risk Score for each (wallet, asset
//! pair) combination, written by the authorised LedgerLens service account
//! and readable by any other Soroban contract.
#![no_std]

use soroban_sdk::{contract, contractimpl, contracttype, Address, Env, Symbol};

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RiskScore {
    /// 0-100; higher = more suspicious.
    pub score: u32,
    /// True if the Benford's Law engine flagged a non-conforming digit distribution.
    pub benford_flag: bool,
    /// True if the ML ensemble classifier flagged this wallet/pair.
    pub ml_flag: bool,
    /// Ledger timestamp of the last update.
    pub timestamp: u64,
    /// Model confidence, 0-100.
    pub confidence: u32,
}

#[contracttype]
enum DataKey {
    Admin,
    Score(Address, Symbol),
}

#[contract]
pub struct LedgerLensScore;

#[contractimpl]
impl LedgerLensScore {
    /// One-time initialisation: registers the address authorised to call `submit_score`.
    pub fn initialize(env: Env, admin: Address) {
        if env.storage().instance().has(&DataKey::Admin) {
            panic!("already initialized");
        }
        env.storage().instance().set(&DataKey::Admin, &admin);
    }

    /// Register a computed risk score for `wallet` on `asset_pair`.
    ///
    /// Only the authorised LedgerLens service account (set via `initialize`)
    /// may call this.
    pub fn submit_score(
        env: Env,
        wallet: Address,
        asset_pair: Symbol,
        score: u32,
        benford_flag: bool,
        ml_flag: bool,
        confidence: u32,
        timestamp: u64,
    ) {
        let admin: Address = env
            .storage()
            .instance()
            .get(&DataKey::Admin)
            .expect("contract not initialized");
        admin.require_auth();

        if score > 100 || confidence > 100 {
            panic!("score and confidence must be in 0..=100");
        }

        let risk_score = RiskScore {
            score,
            benford_flag,
            ml_flag,
            timestamp,
            confidence,
        };

        env.storage()
            .persistent()
            .set(&DataKey::Score(wallet, asset_pair), &risk_score);
    }

    /// Return the most recent LedgerLens risk score for `wallet` on `asset_pair`.
    ///
    /// Callable by any contract or external client; returns `None` if no
    /// score has been submitted yet.
    pub fn get_score(env: Env, wallet: Address, asset_pair: Symbol) -> Option<RiskScore> {
        env.storage()
            .persistent()
            .get(&DataKey::Score(wallet, asset_pair))
    }
}

#[cfg(test)]
mod test {
    use super::*;
    use soroban_sdk::testutils::Address as _;

    #[test]
    fn submit_and_read_score() {
        let env = Env::default();
        let contract_id = env.register_contract(None, LedgerLensScore);
        let client = LedgerLensScoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let wallet = Address::generate(&env);
        let pair = Symbol::new(&env, "XLM_USDC");

        client.initialize(&admin);

        env.mock_all_auths();
        client.submit_score(&wallet, &pair, &70, &true, &true, &82, &1_700_000_000);

        let score = client.get_score(&wallet, &pair).unwrap();
        assert_eq!(score.score, 70);
        assert!(score.benford_flag);
        assert!(score.ml_flag);
        assert_eq!(score.confidence, 82);
        assert_eq!(score.timestamp, 1_700_000_000);
    }

    #[test]
    fn unknown_wallet_returns_none() {
        let env = Env::default();
        let contract_id = env.register_contract(None, LedgerLensScore);
        let client = LedgerLensScoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let wallet = Address::generate(&env);
        let pair = Symbol::new(&env, "XLM_USDC");

        client.initialize(&admin);

        assert!(client.get_score(&wallet, &pair).is_none());
    }
}
