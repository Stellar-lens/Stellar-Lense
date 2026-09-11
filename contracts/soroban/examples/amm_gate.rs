//! Reference integration: gating an AMM swap on a StellarLense risk score.
//!
//! `StellarLenseGatedAmm` is a deliberately minimal contract — it is **not** a
//! real AMM. It exists purely to demonstrate the canonical composability
//! pattern from `docs/interface-spec.md`: call [`query_risk_gate`] inside your
//! guard clause and refuse to proceed for risky wallets.
//!
//! The key property exercised here is that `query_risk_gate` is **infallible**
//! and **side-effect free**. The AMM can call it from inside `swap` without a
//! `try_*` wrapper, without worrying about error propagation, and without any
//! risk that StellarLense could panic and burn the AMM's gas or brick its guard.
//! A consumer can also discover the published capability surface via
//! `get_interface_metadata` and use the `fail_closed` constraint to reason
//! about how unknown wallets and low-confidence scores should be handled.
//!
//! Build it as part of the workspace:
//!
//! ```text
//! cargo build --example amm_gate -p stellar_lense-score
//! ```
//!
//! [`query_risk_gate`]: stellar_lense_score::StellarLenseScoreContract::query_risk_gate

#![no_std]

use stellar_lense_score::StellarLenseScoreContractClient;
use soroban_sdk::{
    contract, contracterror, contractimpl, contracttype, symbol_short, Address, Env,
};

/// Errors surfaced by the gated AMM. `HighRiskWallet` is the one produced by
/// the StellarLense guard clause; the rest are ordinary AMM bookkeeping.
#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(u32)]
pub enum AmmError {
    /// The contract has not been pointed at a StellarLense deployment yet.
    NotConfigured = 1,
    /// StellarLense reports this wallet's risk score is at or above the gate
    /// threshold (or no score exists) — the swap is refused.
    HighRiskWallet = 2,
    /// Swap amount must be positive.
    InvalidAmount = 3,
}

#[contracttype]
enum DataKey {
    /// Contract ID of the StellarLense score registry this AMM trusts.
    StellarLense,
}

/// The risk threshold this AMM enforces: wallets scoring `>= 75` (out of 100)
/// are turned away. Chosen to match StellarLense's own default risk threshold.
const GATE_THRESHOLD: u32 = 75;

#[contract]
pub struct StellarLenseGatedAmm;

#[contractimpl]
impl StellarLenseGatedAmm {
    /// One-time wiring: record which StellarLense deployment to consult.
    ///
    /// A production AMM would protect this behind admin auth; omitted here to
    /// keep the example focused on the gating pattern.
    pub fn initialize(env: Env, stellar_lense: Address) {
        env.storage().instance().set(&DataKey::StellarLense, &stellar_lense);
    }

    /// Process a swap, but only after clearing the swapper through StellarLense.
    ///
    /// This is the pattern integrators should copy: build the generated client
    /// for the StellarLense contract, ask `query_risk_gate`, and bail out with
    /// your own domain error if the wallet is not safe. Note there is no
    /// `try_query_risk_gate` and no `?` — the gate cannot fail.
    pub fn swap(env: Env, user: Address, amount: i128) -> Result<(), AmmError> {
        if amount <= 0 {
            return Err(AmmError::InvalidAmount);
        }

        let llens_contract: Address =
            env.storage().instance().get(&DataKey::StellarLense).ok_or(AmmError::NotConfigured)?;

        let client = StellarLenseScoreContractClient::new(&env, &llens_contract);

        let is_safe = client.query_risk_gate(&user, &symbol_short!("XLM_USDC"), &GATE_THRESHOLD);
        if !is_safe {
            return Err(AmmError::HighRiskWallet);
        }

        // ... rest of swap logic (reserves, pricing, transfers) would go here.
        Ok(())
    }
}
