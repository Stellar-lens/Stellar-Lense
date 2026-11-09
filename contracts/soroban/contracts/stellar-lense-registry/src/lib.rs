#![no_std]
// Contract entry points are the on-chain ABI; their argument lists are the
// call shape integrators use, not something to bundle into structs.
#![allow(clippy::too_many_arguments)]

//! Stellar Lense risk-score registry (v2).
//!
//! A small on-chain registry of wash-trading risk scores published by the
//! Stellar Lense pipeline, for other contracts to gate on.
//!
//! * Authorised **signers** (the off-chain publisher's accounts) write
//!   per-wallet scores and per-pair aggregates.
//! * Anyone reads them: [`get_score`], [`get_pair_score`], [`is_flagged`],
//!   and [`check`], a risk gate that also enforces a maximum score age.
//! * One **admin** manages signers, the flag threshold, pausing, upgrades
//!   and its own (two-step) rotation.
//!
//! Pausing stops writes only; reads keep working so integrations don't
//! break during an incident.
//!
//! Pairs are identified by the same string the API uses, e.g.
//! `XLM/USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN`.
//!
//! [`get_score`]: RiskRegistry::get_score
//! [`get_pair_score`]: RiskRegistry::get_pair_score
//! [`is_flagged`]: RiskRegistry::is_flagged
//! [`check`]: RiskRegistry::check

use soroban_sdk::{
    contract, contracterror, contractimpl, contracttype, symbol_short, Address, BytesN, Env,
    String, Vec,
};

pub const VERSION: u32 = 2;
pub const MAX_SCORE: u32 = 100;
pub const MAX_BATCH: u32 = 50;
pub const DEFAULT_THRESHOLD: u32 = 70;
pub const MAX_PAIR_LEN: u32 = 128;

// Ledgers close every ~5s: keep entries alive ~30 days, re-extend when
// fewer than ~7 days remain.
const DAY_IN_LEDGERS: u32 = 17_280;
const TTL_EXTEND_TO: u32 = 30 * DAY_IN_LEDGERS;
const TTL_THRESHOLD: u32 = 7 * DAY_IN_LEDGERS;

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    AlreadyInitialized = 1,
    NotInitialized = 2,
    NotAdmin = 3,
    NotSigner = 4,
    Paused = 5,
    InvalidScore = 6,
    InvalidConfidence = 7,
    InvalidThreshold = 8,
    BatchTooLarge = 9,
    /// A submission's `as_of` is older than the stored one for that key.
    StaleSubmission = 10,
    NoPendingAdmin = 11,
    InvalidPair = 12,
    NoSigners = 13,
    InvalidPairScore = 14,
}

/// How a score was produced off-chain.
#[contracttype]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(u32)]
pub enum Method {
    Heuristic = 0,
    Ml = 1,
}

/// Latest risk score for one wallet on one pair.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Score {
    /// 0-100, higher = more wash-trading-like.
    pub score: u32,
    /// 0-100, how much evidence backs the score.
    pub confidence: u32,
    pub method: Method,
    /// Unix seconds: close time of the newest trade the score is based on.
    pub as_of: u64,
    /// Ledger sequence when it was written.
    pub updated_ledger: u32,
}

/// Input row for [`RiskRegistry::submit_scores`].
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScoreInput {
    pub wallet: Address,
    pub pair: String,
    pub score: u32,
    pub confidence: u32,
    pub method: Method,
    pub as_of: u64,
}

/// Aggregate over every wallet scored on a pair in one pipeline run.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PairScore {
    pub average: u32,
    pub max: u32,
    /// Wallets at or above the off-chain alert threshold.
    pub flagged: u32,
    pub total: u32,
    pub as_of: u64,
    pub updated_ledger: u32,
}

/// Outcome of [`RiskRegistry::check`].
#[contracttype]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(u32)]
pub enum Decision {
    /// Score exists, is fresh enough, and is below `max_score`.
    Allow = 0,
    /// Score is at or above `max_score`.
    HighRisk = 1,
    /// No score for this wallet/pair. The caller chooses fail-open or closed.
    NoScore = 2,
    /// Score is older than `max_age_secs`.
    Stale = 3,
}

#[contracttype]
#[derive(Clone)]
enum DataKey {
    Admin,
    PendingAdmin,
    Paused,
    Threshold,
    Signer(Address),
    SignerCount,
    Score(Address, String),
    PairScore(String),
}

#[contract]
pub struct RiskRegistry;

fn admin(env: &Env) -> Result<Address, Error> {
    env.storage().instance().get(&DataKey::Admin).ok_or(Error::NotInitialized)
}

fn require_admin(env: &Env, caller: &Address) -> Result<(), Error> {
    caller.require_auth();
    if *caller != admin(env)? {
        return Err(Error::NotAdmin);
    }
    Ok(())
}

fn require_signer(env: &Env, signer: &Address) -> Result<(), Error> {
    admin(env)?;
    signer.require_auth();
    if !env.storage().instance().has(&DataKey::Signer(signer.clone())) {
        return Err(Error::NotSigner);
    }
    if is_paused(env) {
        return Err(Error::Paused);
    }
    Ok(())
}

fn is_paused(env: &Env) -> bool {
    env.storage().instance().get(&DataKey::Paused).unwrap_or(false)
}

fn bump_instance(env: &Env) {
    env.storage().instance().extend_ttl(TTL_THRESHOLD, TTL_EXTEND_TO);
}

fn check_pair(pair: &String) -> Result<(), Error> {
    if pair.is_empty() || pair.len() > MAX_PAIR_LEN {
        return Err(Error::InvalidPair);
    }
    Ok(())
}

fn store_score(env: &Env, input: &ScoreInput) -> Result<(), Error> {
    if input.score > MAX_SCORE {
        return Err(Error::InvalidScore);
    }
    if input.confidence > MAX_SCORE {
        return Err(Error::InvalidConfidence);
    }
    check_pair(&input.pair)?;
    let key = DataKey::Score(input.wallet.clone(), input.pair.clone());
    let store = env.storage().persistent();
    if let Some(existing) = store.get::<_, Score>(&key) {
        if input.as_of < existing.as_of {
            return Err(Error::StaleSubmission);
        }
    }
    let record = Score {
        score: input.score,
        confidence: input.confidence,
        method: input.method,
        as_of: input.as_of,
        updated_ledger: env.ledger().sequence(),
    };
    store.set(&key, &record);
    store.extend_ttl(&key, TTL_THRESHOLD, TTL_EXTEND_TO);
    env.events().publish(
        (symbol_short!("score"), input.wallet.clone()),
        (input.pair.clone(), input.score, input.as_of),
    );
    Ok(())
}

#[contractimpl]
impl RiskRegistry {
    // ── setup ────────────────────────────────────────────────────────────────

    /// One-time setup. `signers` are the accounts allowed to publish scores.
    pub fn initialize(
        env: Env,
        admin: Address,
        signers: Vec<Address>,
        threshold: u32,
    ) -> Result<(), Error> {
        let instance = env.storage().instance();
        if instance.has(&DataKey::Admin) {
            return Err(Error::AlreadyInitialized);
        }
        if threshold > MAX_SCORE {
            return Err(Error::InvalidThreshold);
        }
        if signers.is_empty() {
            return Err(Error::NoSigners);
        }
        admin.require_auth();
        instance.set(&DataKey::Admin, &admin);
        instance.set(&DataKey::Threshold, &threshold);
        instance.set(&DataKey::Paused, &false);
        let mut count: u32 = 0;
        for signer in signers.iter() {
            if !instance.has(&DataKey::Signer(signer.clone())) {
                instance.set(&DataKey::Signer(signer), &true);
                count += 1;
            }
        }
        instance.set(&DataKey::SignerCount, &count);
        bump_instance(&env);
        env.events().publish((symbol_short!("init"),), (admin, count, threshold));
        Ok(())
    }

    // ── writes (signers) ─────────────────────────────────────────────────────

    pub fn submit_score(
        env: Env,
        signer: Address,
        wallet: Address,
        pair: String,
        score: u32,
        confidence: u32,
        method: Method,
        as_of: u64,
    ) -> Result<(), Error> {
        require_signer(&env, &signer)?;
        store_score(&env, &ScoreInput { wallet, pair, score, confidence, method, as_of })?;
        bump_instance(&env);
        Ok(())
    }

    /// Up to [`MAX_BATCH`] scores in one transaction; all-or-nothing.
    pub fn submit_scores(env: Env, signer: Address, scores: Vec<ScoreInput>) -> Result<(), Error> {
        require_signer(&env, &signer)?;
        if scores.len() > MAX_BATCH {
            return Err(Error::BatchTooLarge);
        }
        for input in scores.iter() {
            store_score(&env, &input)?;
        }
        bump_instance(&env);
        Ok(())
    }

    pub fn submit_pair_score(
        env: Env,
        signer: Address,
        pair: String,
        average: u32,
        max: u32,
        flagged: u32,
        total: u32,
        as_of: u64,
    ) -> Result<(), Error> {
        require_signer(&env, &signer)?;
        check_pair(&pair)?;
        if average > MAX_SCORE || max > MAX_SCORE || average > max || flagged > total {
            return Err(Error::InvalidPairScore);
        }
        let key = DataKey::PairScore(pair.clone());
        let store = env.storage().persistent();
        if let Some(existing) = store.get::<_, PairScore>(&key) {
            if as_of < existing.as_of {
                return Err(Error::StaleSubmission);
            }
        }
        store.set(
            &key,
            &PairScore {
                average,
                max,
                flagged,
                total,
                as_of,
                updated_ledger: env.ledger().sequence(),
            },
        );
        store.extend_ttl(&key, TTL_THRESHOLD, TTL_EXTEND_TO);
        bump_instance(&env);
        env.events().publish((symbol_short!("pair"),), (pair, average, max, as_of));
        Ok(())
    }

    // ── reads (anyone) ───────────────────────────────────────────────────────

    pub fn get_score(env: Env, wallet: Address, pair: String) -> Option<Score> {
        env.storage().persistent().get(&DataKey::Score(wallet, pair))
    }

    pub fn get_pair_score(env: Env, pair: String) -> Option<PairScore> {
        env.storage().persistent().get(&DataKey::PairScore(pair))
    }

    /// True if a score exists and is at or above the registry's threshold.
    pub fn is_flagged(env: Env, wallet: Address, pair: String) -> bool {
        let threshold = Self::threshold(env.clone());
        Self::get_score(env, wallet, pair).is_some_and(|s| s.score >= threshold)
    }

    /// Risk gate for integrating contracts: `HighRisk` if the score is at or
    /// above `max_score`, `Stale` if it is older than `max_age_secs` (by
    /// ledger time), `NoScore` if none exists, otherwise `Allow`.
    pub fn check(
        env: Env,
        wallet: Address,
        pair: String,
        max_score: u32,
        max_age_secs: u64,
    ) -> Decision {
        match Self::get_score(env.clone(), wallet, pair) {
            None => Decision::NoScore,
            Some(s) if env.ledger().timestamp().saturating_sub(s.as_of) > max_age_secs => {
                Decision::Stale
            }
            Some(s) if s.score >= max_score => Decision::HighRisk,
            Some(_) => Decision::Allow,
        }
    }

    // ── admin ────────────────────────────────────────────────────────────────

    pub fn add_signer(env: Env, admin: Address, signer: Address) -> Result<(), Error> {
        require_admin(&env, &admin)?;
        let instance = env.storage().instance();
        if !instance.has(&DataKey::Signer(signer.clone())) {
            instance.set(&DataKey::Signer(signer.clone()), &true);
            let count: u32 = instance.get(&DataKey::SignerCount).unwrap_or(0);
            instance.set(&DataKey::SignerCount, &(count + 1));
        }
        bump_instance(&env);
        env.events().publish((symbol_short!("sig_add"),), signer);
        Ok(())
    }

    /// Removing the last signer is refused, so the registry can't be left
    /// unable to publish.
    pub fn remove_signer(env: Env, admin: Address, signer: Address) -> Result<(), Error> {
        require_admin(&env, &admin)?;
        let instance = env.storage().instance();
        if instance.has(&DataKey::Signer(signer.clone())) {
            let count: u32 = instance.get(&DataKey::SignerCount).unwrap_or(0);
            if count <= 1 {
                return Err(Error::NoSigners);
            }
            instance.remove(&DataKey::Signer(signer.clone()));
            instance.set(&DataKey::SignerCount, &(count - 1));
        }
        bump_instance(&env);
        env.events().publish((symbol_short!("sig_rm"),), signer);
        Ok(())
    }

    pub fn set_threshold(env: Env, admin: Address, threshold: u32) -> Result<(), Error> {
        require_admin(&env, &admin)?;
        if threshold > MAX_SCORE {
            return Err(Error::InvalidThreshold);
        }
        env.storage().instance().set(&DataKey::Threshold, &threshold);
        bump_instance(&env);
        env.events().publish((symbol_short!("thresh"),), threshold);
        Ok(())
    }

    pub fn pause(env: Env, admin: Address) -> Result<(), Error> {
        require_admin(&env, &admin)?;
        env.storage().instance().set(&DataKey::Paused, &true);
        env.events().publish((symbol_short!("paused"),), true);
        Ok(())
    }

    pub fn unpause(env: Env, admin: Address) -> Result<(), Error> {
        require_admin(&env, &admin)?;
        env.storage().instance().set(&DataKey::Paused, &false);
        env.events().publish((symbol_short!("paused"),), false);
        Ok(())
    }

    /// Step 1 of admin rotation: the current admin nominates a successor.
    pub fn propose_admin(env: Env, admin: Address, new_admin: Address) -> Result<(), Error> {
        require_admin(&env, &admin)?;
        env.storage().instance().set(&DataKey::PendingAdmin, &new_admin);
        env.events().publish((symbol_short!("adm_prop"),), new_admin);
        Ok(())
    }

    /// Step 2: the nominee accepts, proving it controls the new key.
    pub fn accept_admin(env: Env) -> Result<(), Error> {
        let instance = env.storage().instance();
        let pending: Address = instance.get(&DataKey::PendingAdmin).ok_or(Error::NoPendingAdmin)?;
        pending.require_auth();
        instance.set(&DataKey::Admin, &pending);
        instance.remove(&DataKey::PendingAdmin);
        bump_instance(&env);
        env.events().publish((symbol_short!("adm_acc"),), pending);
        Ok(())
    }

    /// Replace this contract's code. Storage is kept.
    pub fn upgrade(env: Env, admin: Address, new_wasm_hash: BytesN<32>) -> Result<(), Error> {
        require_admin(&env, &admin)?;
        env.deployer().update_current_contract_wasm(new_wasm_hash.clone());
        env.events().publish((symbol_short!("upgrade"),), new_wasm_hash);
        Ok(())
    }

    // ── introspection ────────────────────────────────────────────────────────

    pub fn admin(env: Env) -> Result<Address, Error> {
        admin(&env)
    }

    pub fn pending_admin(env: Env) -> Option<Address> {
        env.storage().instance().get(&DataKey::PendingAdmin)
    }

    pub fn is_signer(env: Env, account: Address) -> bool {
        env.storage().instance().has(&DataKey::Signer(account))
    }

    pub fn is_paused(env: Env) -> bool {
        is_paused(&env)
    }

    pub fn threshold(env: Env) -> u32 {
        env.storage().instance().get(&DataKey::Threshold).unwrap_or(DEFAULT_THRESHOLD)
    }

    pub fn version(_env: Env) -> u32 {
        VERSION
    }
}

#[cfg(test)]
mod test;
