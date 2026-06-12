use soroban_sdk::{Address, Env, Symbol};

use crate::types::{DataKey, RiskScore};

/// Persistent storage entries are bumped to keep risk scores alive
/// for ~30 days of inactivity, extending to ~45 days on access.
const SCORE_TTL_THRESHOLD: u32 = 518_400; // ~30 days at 5s/ledger
const SCORE_TTL_EXTEND_TO: u32 = 777_600; // ~45 days at 5s/ledger

pub fn has_admin(env: &Env) -> bool {
    env.storage().instance().has(&DataKey::Admin)
}

pub fn set_admin(env: &Env, admin: &Address) {
    env.storage().instance().set(&DataKey::Admin, admin);
}

pub fn get_admin(env: &Env) -> Address {
    env.storage().instance().get(&DataKey::Admin).unwrap()
}

pub fn set_service(env: &Env, service: &Address) {
    env.storage().instance().set(&DataKey::Service, service);
}

pub fn get_service(env: &Env) -> Address {
    env.storage().instance().get(&DataKey::Service).unwrap()
}

pub fn set_score(env: &Env, wallet: &Address, asset_pair: &Symbol, score: &RiskScore) {
    let key = DataKey::Score(wallet.clone(), asset_pair.clone());
    env.storage().persistent().set(&key, score);
    env.storage().persistent().extend_ttl(&key, SCORE_TTL_THRESHOLD, SCORE_TTL_EXTEND_TO);
}

pub fn get_score(env: &Env, wallet: &Address, asset_pair: &Symbol) -> Option<RiskScore> {
    let key = DataKey::Score(wallet.clone(), asset_pair.clone());
    let score = env.storage().persistent().get(&key);
    if score.is_some() {
        env.storage().persistent().extend_ttl(&key, SCORE_TTL_THRESHOLD, SCORE_TTL_EXTEND_TO);
    }
    score
}
