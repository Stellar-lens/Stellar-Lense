#![no_std]

#[cfg(test)]
extern crate std;

#[cfg(test)]
mod test;

use soroban_sdk::{contract, contractimpl, contracterror, contracttype, symbol_short, vec, Address, Env, Symbol, Vec};
use ledgerlens_score::{AggregateRiskScore, RiskScore};

pub const MAX_SHARDS: usize = 10;

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    AlreadyInitialized = 1,
    NotInitialized = 2,
    Unauthorized = 3,
    SelfReference = 4,
    ShardAlreadyRegistered = 5,
    ShardNotRegistered = 6,
    ShardLimitReached = 7,
    ScoreNotFound = 8,
    NoShards = 9,
    ShardFailure = 10,
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

    pub fn get_decay_rate(_env: Env) -> (u64, u64) {
        const DECAY_NUMERATOR: u64 = 999;
        const DECAY_DENOMINATOR: u64 = 1000;
        (DECAY_NUMERATOR, DECAY_DENOMINATOR)
    }

    pub fn get_consensus_threshold_k(_env: Env) -> u32 {
        const CONSENSUS_THRESHOLD_K: u32 = 5;
        CONSENSUS_THRESHOLD_K
    }

    pub fn get_watchlist_status(_env: Env, _wallet: Address) -> bool {
        false
    }

    pub fn add_shard(env: Env, shard: Address) -> Result<(), Error> {
        let admin: Address = env.storage().instance().get(&DataKey::Admin).ok_or(Error::NotInitialized)?;
        admin.require_auth();
        if env.current_contract_address() == shard {
            return Err(Error::SelfReference);
        }
        let mut shards: Vec<Address> = env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        for i in 0..shards.len() {
            if shards.get(i).unwrap() == shard {
                return Err(Error::ShardAlreadyRegistered);
            }
        }
        if shards.len() as usize >= MAX_SHARDS {
            return Err(Error::ShardLimitReached);
        }
        shards.push_back(shard);
        env.storage().instance().set(&DataKey::Shards, &shards);
        Ok(())
    }

    pub fn remove_shard(env: Env, shard: Address) -> Result<(), Error> {
        let admin: Address = env.storage().instance().get(&DataKey::Admin).ok_or(Error::NotInitialized)?;
        admin.require_auth();
        let shards: Vec<Address> = env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
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
        Ok(())
    }

    pub fn get_shards(env: Env) -> Vec<Address> {
        env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env))
    }

    pub fn query_risk_gate(env: Env, wallet: Address, asset_pair: Symbol, gate_threshold: u32) -> Result<bool, Error> {
        let shards: Vec<Address> = env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        if shards.is_empty() {
            return Err(Error::NoShards);
        }
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_query_risk_gate(&wallet, &asset_pair, &gate_threshold) {
                Ok(Ok(true)) => {}
                Ok(Ok(false)) => return Ok(false),
                _ => {
                    env.storage().instance().set(&DataKey::LastShardFailure, &(shard.clone(), 0u32));
                    return Err(Error::ShardFailure);
                }
            }
        }
        Ok(true)
    }

    pub fn get_score(env: Env, wallet: Address, asset_pair: Symbol) -> Result<RiskScore, Error> {
        let shards: Vec<Address> = env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut best: Option<RiskScore> = None;
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_get_score(&wallet, &asset_pair) {
                Ok(Ok(score)) => {
                    match &best {
                        None => best = Some(score),
                        Some(b) => {
                            if score.score > b.score {
                                best = Some(score);
                            }
                        }
                    }
                }
                Ok(Err(_conv_err)) => {
                    env.storage().instance().set(&DataKey::LastShardFailure, &(shard.clone(), 1u32));
                }
                Err(_) => {
                    env.storage().instance().set(&DataKey::LastShardFailure, &(shard.clone(), 0u32));
                }
            }
        }
        best.ok_or(Error::ScoreNotFound)
    }

    pub fn get_aggregate_score(env: Env, wallet: Address) -> Result<AggregateRiskScore, Error> {
        let shards: Vec<Address> = env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut best: Option<AggregateRiskScore> = None;
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_get_aggregate_score(&wallet) {
                Ok(Ok(agg)) => {
                    match &best {
                        None => best = Some(agg),
                        Some(b) => {
                            if agg.aggregate_score > b.aggregate_score {
                                best = Some(agg);
                            }
                        }
                    }
                }
                Ok(Err(_conv_err)) => {
                    env.storage().instance().set(&DataKey::LastShardFailure, &(shard.clone(), 1u32));
                }
                Err(_) => {
                    env.storage().instance().set(&DataKey::LastShardFailure, &(shard.clone(), 0u32));
                }
            }
        }
        best.ok_or(Error::ScoreNotFound)
    }

    pub fn supports_interface(env: Env, capability: Symbol) -> bool {
        let caps = vec![&env, symbol_short!("score"), symbol_short!("gate"), symbol_short!("aggr"), symbol_short!("federated")];
        for i in 0..caps.len() {
            if caps.get(i).unwrap() == capability {
                return true;
            }
        }
        false
    }

    pub fn get_score_across_shards(env: Env, wallet: Address, asset_pair: Symbol) -> Vec<(Address, Option<RiskScore>)> {
        let shards: Vec<Address> = env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut out: Vec<(Address, Option<RiskScore>)> = Vec::new(&env);
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_get_score(&wallet, &asset_pair) {
                Ok(Ok(score)) => out.push_back((shard.clone(), Some(score))),
                _ => out.push_back((shard.clone(), None)),
            }
        }
        out
    }

    pub fn contagion_depth_across_shards(
        env: Env,
        wallet: Address,
        asset_pair: Symbol,
    ) -> u32 {
        let shards: Vec<Address> = env.storage().instance().get(&DataKey::Shards).unwrap_or_else(|| Vec::new(&env));
        let mut max_depth: u32 = 0;
        for i in 0..shards.len() {
            let shard = shards.get(i).unwrap();
            let client = ledgerlens_score::LedgerLensScoreContractClient::new(&env, &shard);
            match client.try_get_contagion_depth(&wallet, &asset_pair) {
                Ok(Ok(depth)) => {
                    if depth > max_depth {
                        max_depth = depth;
                    }
                }
                _ => {
                    env.storage().instance().set(&DataKey::LastShardFailure, &(shard.clone(), 0u32));
                }
            }
        }
        max_depth
    }

    pub fn get_last_shard_failure(env: Env) -> Option<(Address, u32)> {
        env.storage().instance().get(&DataKey::LastShardFailure)
    }
}

#[contracttype]
#[derive(Clone)]
enum DataKey {
    Admin,
    Shards,
    LastShardFailure,
}
