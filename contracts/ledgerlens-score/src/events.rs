use soroban_sdk::{symbol_short, Address, Env, Symbol};

use crate::types::RiskScore;

// ── Aggregate risk ────────────────────────────────────────────────────────────

/// Emitted when the admin sets a per-asset-pair weight via `set_pair_weight`.
pub fn pair_weight_updated(env: &Env, asset_pair: &Symbol, weight: u32) {
    env.events().publish((symbol_short!("pw_upd"), asset_pair.clone()), weight);
}

// ── Score events ─────────────────────────────────────────────────────────────

pub fn score_submitted(env: &Env, wallet: &Address, asset_pair: &Symbol, score: &RiskScore) {
    env.events().publish(
        (symbol_short!("score"), wallet.clone(), asset_pair.clone()),
        (score.score, score.benford_flag, score.ml_flag, score.confidence, score.timestamp),
    );
}

// ── Service rotation ──────────────────────────────────────────────────────────

pub fn service_updated(env: &Env, new_service: &Address) {
    env.events().publish((symbol_short!("svc_upd"),), new_service.clone());
}

// ── Pause circuit breaker ────────────────────────────────────────────────────

pub fn contract_paused(env: &Env, by: &Address) {
    env.events().publish((symbol_short!("paused"),), by.clone());
}

pub fn contract_unpaused(env: &Env, by: &Address) {
    env.events().publish((symbol_short!("unpaused"),), by.clone());
}

// ── Two-step admin transfer ──────────────────────────────────────────────────

pub fn admin_transfer_initiated(env: &Env, from: &Address, to: &Address) {
    env.events().publish((symbol_short!("adm_init"),), (from.clone(), to.clone()));
}

pub fn admin_transfer_accepted(env: &Env, new_admin: &Address) {
    env.events().publish((symbol_short!("adm_done"),), new_admin.clone());
}

pub fn admin_transfer_cancelled(env: &Env, admin: &Address) {
    env.events().publish((symbol_short!("adm_canc"),), admin.clone());
}

// ── Watchlist ────────────────────────────────────────────────────────────────

pub fn watchlist_updated(env: &Env, wallet: &Address, flagged: bool) {
    env.events().publish((symbol_short!("watch"),), (wallet.clone(), flagged));
}

// ── Risk threshold ───────────────────────────────────────────────────────────

pub fn threshold_updated(env: &Env, old_threshold: u32, new_threshold: u32) {
    env.events().publish((symbol_short!("thresh"),), (old_threshold, new_threshold));
}

/// Emitted inside `submit_score` / `submit_scores_batch` when a
/// submitted score meets or exceeds the configured risk threshold.
/// Off-chain indexers should subscribe to this for real-time alerting.
pub fn threshold_breached(
    env: &Env,
    wallet: &Address,
    asset_pair: &Symbol,
    score: u32,
    threshold: u32,
) {
    env.events()
        .publish((symbol_short!("breach"), wallet.clone()), (asset_pair.clone(), score, threshold));
}
