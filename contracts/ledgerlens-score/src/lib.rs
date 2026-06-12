#![no_std]

mod errors;
mod events;
mod storage;
mod types;

#[cfg(test)]
mod test;

use soroban_sdk::{contract, contractimpl, Address, Env, Symbol};

pub use errors::Error;
pub use types::RiskScore;

/// On-chain truth layer for LedgerLens risk scores.
///
/// The off-chain detection pipeline (Benford's Law engine + ML
/// ensemble) computes a 0-100 risk score per wallet / asset-pair and
/// writes it here via `submit_score`. Any Soroban contract can then
/// read that score via `get_score` to gate suspicious activity.
#[contract]
pub struct LedgerLensScoreContract;

#[contractimpl]
impl LedgerLensScoreContract {
    /// One-time setup. `admin` can rotate the scoring service address;
    /// `service` is the off-chain LedgerLens account authorised to
    /// submit scores.
    pub fn initialize(env: Env, admin: Address, service: Address) -> Result<(), Error> {
        if storage::has_admin(&env) {
            return Err(Error::AlreadyInitialized);
        }

        storage::set_admin(&env, &admin);
        storage::set_service(&env, &service);

        Ok(())
    }

    /// Register a freshly computed risk score for `wallet` /
    /// `asset_pair`. Requires authorization from the configured
    /// scoring service account.
    #[allow(clippy::too_many_arguments)]
    pub fn submit_score(
        env: Env,
        wallet: Address,
        asset_pair: Symbol,
        score: u32,
        benford_flag: bool,
        ml_flag: bool,
        timestamp: u64,
        confidence: u32,
    ) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }

        let service = storage::get_service(&env);
        service.require_auth();

        if score > 100 {
            return Err(Error::InvalidScore);
        }
        if confidence > 100 {
            return Err(Error::InvalidConfidence);
        }

        let risk_score = RiskScore { score, benford_flag, ml_flag, timestamp, confidence };

        storage::set_score(&env, &wallet, &asset_pair, &risk_score);
        events::score_submitted(&env, &wallet, &asset_pair, &risk_score);

        Ok(())
    }

    /// Read-only lookup of the latest risk score for `wallet` /
    /// `asset_pair`. Callable by any account or contract.
    pub fn get_score(env: Env, wallet: Address, asset_pair: Symbol) -> Result<RiskScore, Error> {
        storage::get_score(&env, &wallet, &asset_pair).ok_or(Error::ScoreNotFound)
    }

    /// Rotate the authorised off-chain scoring service address.
    /// Admin only.
    pub fn set_service(env: Env, new_service: Address) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }

        storage::get_admin(&env).require_auth();
        storage::set_service(&env, &new_service);
        events::service_updated(&env, &new_service);

        Ok(())
    }

    /// Returns the current admin address.
    pub fn get_admin(env: Env) -> Result<Address, Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }

        Ok(storage::get_admin(&env))
    }

    /// Returns the current authorised scoring service address.
    pub fn get_service(env: Env) -> Result<Address, Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }

        Ok(storage::get_service(&env))
    }
}
