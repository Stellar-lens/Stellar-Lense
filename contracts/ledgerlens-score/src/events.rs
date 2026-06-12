use soroban_sdk::{symbol_short, Address, Env, Symbol};

use crate::types::RiskScore;

/// Emitted whenever the off-chain LedgerLens service writes a new
/// risk score for a wallet / asset-pair pair.
pub fn score_submitted(env: &Env, wallet: &Address, asset_pair: &Symbol, score: &RiskScore) {
    env.events().publish(
        (symbol_short!("score"), wallet.clone(), asset_pair.clone()),
        (score.score, score.benford_flag, score.ml_flag, score.confidence, score.timestamp),
    );
}

/// Emitted when the admin rotates the authorised scoring service address.
pub fn service_updated(env: &Env, new_service: &Address) {
    env.events().publish((symbol_short!("svc_upd"),), new_service.clone());
}
