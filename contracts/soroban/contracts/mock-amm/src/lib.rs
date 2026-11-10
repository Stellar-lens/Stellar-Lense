#![no_std]

//! How a protocol uses the Stellar Lense registry.
//!
//! An AMM-shaped contract (no reserves, no pricing; it only decides whether
//! a swap may proceed) that asks the registry's risk gate before letting a
//! wallet trade a pair:
//!
//! ```text
//! registry.check(trader, pair, max_score, max_age_secs)
//!   Allow    -> swap proceeds
//!   HighRisk -> refused
//!   Stale    -> refused unless the AMM opted into fail-open
//!   NoScore  -> refused unless the AMM opted into fail-open
//! ```
//!
//! The registry is declared below as a one-function client trait, so this
//! contract's Wasm contains none of the registry's code.

use soroban_sdk::{
    contract, contractclient, contracterror, contractimpl, contracttype, symbol_short, Address,
    Env, String,
};

/// Mirror of `stellar_lense_registry::Decision` (same u32 discriminants).
#[contracttype]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(u32)]
pub enum Decision {
    Allow = 0,
    HighRisk = 1,
    NoScore = 2,
    Stale = 3,
}

#[contractclient(name = "RegistryClient")]
pub trait Registry {
    fn check(
        env: Env,
        wallet: Address,
        pair: String,
        max_score: u32,
        max_age_secs: u64,
    ) -> Decision;
}

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    NotConfigured = 1,
    AlreadyInitialized = 2,
    NotAdmin = 3,
    InvalidAmount = 4,
    HighRiskWallet = 5,
    StaleScore = 6,
    NoScore = 7,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Config {
    pub registry: Address,
    /// Refuse wallets scoring at or above this (0-100).
    pub max_score: u32,
    /// Refuse scores older than this many seconds.
    pub max_age_secs: u64,
    /// Let wallets with no score, or a stale one, trade anyway.
    pub fail_open: bool,
}

#[contracttype]
enum DataKey {
    Admin,
    Config,
}

#[contract]
pub struct MockAmm;

fn config(env: &Env) -> Result<Config, Error> {
    env.storage().instance().get(&DataKey::Config).ok_or(Error::NotConfigured)
}

#[contractimpl]
impl MockAmm {
    pub fn initialize(
        env: Env,
        admin: Address,
        registry: Address,
        max_score: u32,
        max_age_secs: u64,
    ) -> Result<(), Error> {
        if env.storage().instance().has(&DataKey::Admin) {
            return Err(Error::AlreadyInitialized);
        }
        admin.require_auth();
        env.storage().instance().set(&DataKey::Admin, &admin);
        env.storage()
            .instance()
            .set(&DataKey::Config, &Config { registry, max_score, max_age_secs, fail_open: false });
        Ok(())
    }

    pub fn set_fail_open(env: Env, admin: Address, fail_open: bool) -> Result<(), Error> {
        admin.require_auth();
        let stored: Address =
            env.storage().instance().get(&DataKey::Admin).ok_or(Error::NotConfigured)?;
        if stored != admin {
            return Err(Error::NotAdmin);
        }
        let mut cfg = config(&env)?;
        cfg.fail_open = fail_open;
        env.storage().instance().set(&DataKey::Config, &cfg);
        Ok(())
    }

    /// What the gate would decide for `trader` right now (no auth, no state change).
    pub fn preview(env: Env, trader: Address, pair: String) -> Result<Decision, Error> {
        let cfg = config(&env)?;
        Ok(RegistryClient::new(&env, &cfg.registry).check(
            &trader,
            &pair,
            &cfg.max_score,
            &cfg.max_age_secs,
        ))
    }

    /// Accepts the swap (returning `amount`) only if the registry's gate allows it.
    pub fn swap(env: Env, trader: Address, pair: String, amount: i128) -> Result<i128, Error> {
        trader.require_auth();
        if amount <= 0 {
            return Err(Error::InvalidAmount);
        }
        let cfg = config(&env)?;
        let decision = RegistryClient::new(&env, &cfg.registry).check(
            &trader,
            &pair,
            &cfg.max_score,
            &cfg.max_age_secs,
        );
        match decision {
            Decision::Allow => {}
            Decision::HighRisk => return Err(Error::HighRiskWallet),
            Decision::Stale if !cfg.fail_open => return Err(Error::StaleScore),
            Decision::NoScore if !cfg.fail_open => return Err(Error::NoScore),
            Decision::Stale | Decision::NoScore => {}
        }
        env.events().publish((symbol_short!("swap"), trader), (pair, amount));
        Ok(amount)
    }

    pub fn config(env: Env) -> Result<Config, Error> {
        config(&env)
    }
}

#[cfg(test)]
mod test;
