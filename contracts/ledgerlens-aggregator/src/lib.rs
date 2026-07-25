#![no_std]

#[cfg(test)]
extern crate std;

#[cfg(test)]
mod test;

use ledgerlens_score::{AggregateRiskScore, Error as ScoreError, RiskScore};
use soroban_sdk::{
    contract, contracterror, contractimpl, contracttype, symbol_short, vec, Address, Env, Symbol,
    Vec,
};

pub const MAX_SHARDS: usize = 10;

/// Errors surfaced directly by `LedgerLensAggregator`'s own bookkeeping
/// (shard registry, admin gating). `query_risk_gate` itself is infallible —
/// see its doc comment — and reports every failure case by returning `false`
/// rather than one of these variants. Errors that originate from a specific
/// shard's `ledgerlens-score` deployment (e.g. an incompatible interface) are
/// reported as their own `ledgerlens_score::Error` (`ScoreError`) value
/// instead of being wrapped here.
#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    AlreadyInitialized = 1,
    NotInitialized = 2,
    SelfReference = 3,
    ShardAlreadyRegistered = 4,
    ShardLimitReached = 5,
    ShardNotRegistered = 6,
    /// A candidate shard does not advertise every capability
    /// `REQUIRED_SHARD_CAPABILITIES` requires.
    IncompatibleInterface = 7,
}

/// Capabilities of the `ILedgerLensScore` interface (interface version 2, see
/// `docs/interface-spec.md`) that this aggregator invokes on every registered
/// shard: `query_risk_gate` (`gate`), `get_score` (`score`), and
/// `get_aggregate_score` (`aggr`). `add_shard` requires a candidate shard to
/// advertise all of them via `supports_interface`, so a shard whose interface
/// has drifted is rejected at registration time instead of failing silently
/// during a later cross-contract call.
const REQUIRED_SHARD_CAPABILITIES: [&str; 3] = ["score", "gate", "aggr"];

/// Returns `true` only when `shard` reports support for every capability in
/// [`REQUIRED_SHARD_CAPABILITIES`]. A shard that omits one, reports `false`, or
/// does not expose `supports_interface` at all (an older or drifted build) is
/// treated as incompatible.
fn shard_supports_required_interface(env: &Env, shard: &Address) -> bool {
    let client = ledgerlens_score::LedgerLensScoreContractClient::new(env, shard);
    for capability in REQUIRED_SHARD_CAPABILITIES {
        match client.try_supports_interface(&Symbol::new(env, capability)) {
            Ok(Ok(true)) => {}
            _ => return false,
        }
    }
    true
}

#[contract]
pub struct LedgerLensAggregator;

#[contractimpl]
impl LedgerLensAggregator {
    pub fn initialize(env: Env, admin: Address) -> Result<(), Error> {
        if env.storage().instance().has(&DataKey::Admin) {
            return Err(Error::AlreadyInitialized);
        }
        env.storage().instance().set(&DataKey::Admin, &admin);
        Ok(())
    }

    pub fn get_admin(env: Env) -> Result<Address, Error> {
        env.storage().instance().get(&DataKey::Admin).ok_or(Error::NotInitialized)
    }

    /// Returns the fixed-point exponential decay lambda as (numerator, denominator).
    ///
    /// Aggregation policy: singleton configuration is read from the primary
    /// shard, defined as the first registered shard. If shards diverge, the
    /// aggregator does not average or reconcile the values; operators must keep
    /// shard configuration aligned or intentionally choose the primary shard's
    /// value for integrators.
    ///
    /// Example:
    /// ```ignore
    /// let (num, den) = env.invoke_contract(&contract_id, &symbol_short!("get_decay_rate"), ());
    /// // decay_factor = num / den  (e.g. 999 / 1000 = 0.999)
    /// ```
    pub fn get_decay_rate(env: Env) -> Result<(u64, u64), ScoreError> {
        let shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let primary = shards.get(0).ok_or(ScoreError::ScoreNotFound)?;
        let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &primary);

        match client.try_get_decay_rate() {
            Ok(Ok(rate)) => Ok(rate),
            _ => Err(ScoreError::ScoreNotFound),
        }
    }

    pub fn get_consensus_threshold_k(_env: Env) -> u32 {
        // Adjust this value based on your actual consensus parameters
        const CONSENSUS_THRESHOLD_K: u32 = 5; // Minimum agreeing models required

        CONSENSUS_THRESHOLD_K
    }

    /// Returns whether the given wallet is currently on any shard's monitoring watchlist.
    ///
    /// Aggregation policy: watchlist is a conservative risk signal, so shard
    /// results are OR'd. A wallet is considered watchlisted if any registered
    /// shard reports `true`.
    ///
    /// Example:
    /// ```ignore
    /// let is_watched = env.invoke_contract(&contract_id, &symbol_short!("get_watchlist_status"), vec![&env, wallet]);
    /// ```
    pub fn get_watchlist_status(env: Env, wallet: Address) -> bool {
        let shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            if let Ok(Ok(true)) = client.try_is_watchlisted(&wallet) {
                return true;
            }
        }
        false
    }

    pub fn add_shard(env: Env, shard: Address) -> Result<(), Error> {
        let admin: Address =
            env.storage().instance().get(&DataKey::Admin).ok_or(Error::NotInitialized)?;
        admin.require_auth();
        if env.current_contract_address() == shard {
            return Err(Error::SelfReference);
        }
        let mut shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        // Check duplicate
        for i in 0..shards.len() {
            if shards.get(i).unwrap() == shard {
                return Err(Error::ShardAlreadyRegistered);
            }
        }
        if shards.len() as usize >= MAX_SHARDS {
            return Err(Error::ShardLimitReached);
        }
        if !shard_supports_required_interface(&env, &shard) {
            return Err(Error::IncompatibleInterface);
        }
        shards.push_back(shard);
        env.storage().instance().set(&DataKey::Shards, &shards);
        Ok(())
    }

    pub fn remove_shard(env: Env, shard: Address) -> Result<(), Error> {
        let admin: Address =
            env.storage().instance().get(&DataKey::Admin).ok_or(Error::NotInitialized)?;
        admin.require_auth();
        let shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut found = false;
        let mut out: Vec<Address> = Vec::new(&env);
        for i in 0..shards.len() {
            let a = shards.get(i).unwrap();
            if a == shard {
                found = true;
            } else {
                out.push_back(a);
            }
        }
        if !found {
            return Err(Error::ShardNotRegistered);
        }
        env.storage().instance().set(&DataKey::Shards, &out);
        env.storage().instance().remove(&DataKey::ShardHealth(shard));
        Ok(())
    }

    pub fn get_shards(env: Env) -> Vec<Address> {
        env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env))
    }

    /// Infallible, side-effect-free (beyond recording `LastShardFailure`) gate
    /// check, mirroring `ledgerlens-score`'s own `query_risk_gate`: every
    /// registered, healthy shard must agree the wallet clears `gate_threshold`
    /// (an AND across shards), and any shard that is unhealthy is skipped, but
    /// a shard whose cross-contract call itself fails (unreachable contract,
    /// trap, etc.) fails the *whole* query closed — see
    /// `tests/composability/tests/aggregator_shard_pause.rs` (issue #411).
    pub fn query_risk_gate(
        env: Env,
        wallet: Address,
        asset_pair: Symbol,
        gate_threshold: u32,
    ) -> bool {
        let shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        if shards.is_empty() {
            return false;
        }
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            if !is_shard_healthy(&env, &shard) {
                continue;
            }
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_query_risk_gate(&wallet, &asset_pair, &gate_threshold) {
                Ok(Ok(true)) => {}
                Ok(Ok(false)) => return false,
                _ => {
                    env.storage()
                        .instance()
                        .set(&DataKey::LastShardFailure, &(shard.clone(), 0u32));
                    return false;
                }
            }
        }
        true
    }

    pub fn get_score(
        env: Env,
        wallet: Address,
        asset_pair: Symbol,
    ) -> Result<RiskScore, ScoreError> {
        let shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut best: Option<RiskScore> = None;
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            if !is_shard_healthy(&env, &shard) {
                continue;
            }
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_get_score(&wallet, &asset_pair) {
                Ok(Ok(score)) => match &best {
                    None => best = Some(score),
                    Some(b) => {
                        if score.score > b.score {
                            best = Some(score);
                        }
                    }
                },
                Ok(Err(_conv_err)) => {
                    env.storage()
                        .instance()
                        .set(&DataKey::LastShardFailure, &(shard.clone(), 1u32));
                }
                Err(_) => {
                    env.storage()
                        .instance()
                        .set(&DataKey::LastShardFailure, &(shard.clone(), 0u32));
                }
            }
        }
        best.ok_or(ScoreError::ScoreNotFound)
    }

    pub fn get_aggregate_score(
        env: Env,
        wallet: Address,
    ) -> Result<AggregateRiskScore, ScoreError> {
        let shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut best: Option<AggregateRiskScore> = None;
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            if !is_shard_healthy(&env, &shard) {
                continue;
            }
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_get_aggregate_score(&wallet) {
                Ok(Ok(agg)) => match &best {
                    None => best = Some(agg),
                    Some(b) => {
                        if agg.aggregate_score > b.aggregate_score {
                            best = Some(agg);
                        }
                    }
                },
                Ok(Err(_conv_err)) => {
                    env.storage()
                        .instance()
                        .set(&DataKey::LastShardFailure, &(shard.clone(), 1u32));
                }
                Err(_) => {
                    env.storage()
                        .instance()
                        .set(&DataKey::LastShardFailure, &(shard.clone(), 0u32));
                }
            }
        }
        best.ok_or(ScoreError::ScoreNotFound)
    }

    pub fn supports_interface(env: Env, capability: Symbol) -> bool {
        let caps = vec![
            &env,
            symbol_short!("score"),
            symbol_short!("gate"),
            symbol_short!("aggr"),
            symbol_short!("federated"),
        ];
        for i in 0..caps.len() {
            if caps.get(i).unwrap() == capability {
                return true;
            }
        }
        false
    }

    pub fn get_score_across_shards(
        env: Env,
        wallet: Address,
        asset_pair: Symbol,
    ) -> Vec<(Address, Option<RiskScore>)> {
        let shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut out: Vec<(Address, Option<RiskScore>)> = Vec::new(&env);
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            if !is_shard_healthy(&env, &shard) {
                continue;
            }
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_get_score(&wallet, &asset_pair) {
                Ok(Ok(score)) => out.push_back((shard.clone(), Some(score))),
                _ => out.push_back((shard.clone(), None)),
            }
        }
        out
    }

    /// Queries the contagion depth across all shards, returning the maximum depth found.
    ///
    /// Returns the highest counterparty count for the wallet/pair across all registered shards.
    pub fn contagion_depth_across_shards(env: Env, wallet: Address, asset_pair: Symbol) -> u32 {
        let shards: Vec<Address> =
            env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut max_depth: u32 = 0;
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            if !is_shard_healthy(&env, &shard) {
                continue;
            }
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_get_contagion_depth(&wallet, &asset_pair) {
                Ok(Ok(depth)) => {
                    if depth > max_depth {
                        max_depth = depth;
                    }
                }
                _ => {
                    env.storage()
                        .instance()
                        .set(&DataKey::LastShardFailure, &(shard.clone(), 0u32));
                }
            }
        }
        max_depth
    }

    pub fn get_last_shard_failure(env: Env) -> Option<(Address, u32)> {
        env.storage().instance().get(&DataKey::LastShardFailure)
    }
}

fn is_shard_healthy(env: &Env, shard: &Address) -> bool {
    env.storage().instance().get(&DataKey::ShardHealth(shard.clone())).unwrap_or(true)
}

#[contracttype]
#[derive(Clone)]
enum DataKey {
    Admin,
    Shards,
    LastShardFailure,
    ShardHealth(Address),
}
