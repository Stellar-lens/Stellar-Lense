//! Reference integration: gating AMM liquidity provision on LedgerLens risk
//! score **and** confidence.
//!
//! See also [`examples/amm_gate.rs`](amm_gate.rs) for the score-only swap pattern
//! and `contracts/mock-amm/` for a deployable test fixture exercising the same
//! gate in cross-contract tests.
//!
//! Build:
//!
//! ```text
//! cargo build --example amm_gate_example -p ledgerlens-score
//! ```

#![no_std]

use ledgerlens_score::LedgerLensScoreContractClient;
use soroban_sdk::{
    contract, contracterror, contractimpl, contracttype, symbol_short, Address, Env,
};

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(u32)]
pub enum AmmLiquidityError {
    NotConfigured = 1,
    /// Score too high or no score on file (fail closed).
    HighRiskProvider = 2,
    /// Score exists but confidence is below the pool minimum.
    LowConfidence = 3,
    InvalidAmount = 4,
}

#[contracttype]
enum DataKey {
    LedgerLens,
    GateThreshold,
    MinConfidence,
}

#[contract]
pub struct LedgerLensGatedLiquidity;

#[contractimpl]
impl LedgerLensGatedLiquidity {
    pub fn initialize(env: Env, ledgerlens: Address, gate_threshold: u32, min_confidence: u32) {
        env.storage().instance().set(&DataKey::LedgerLens, &ledgerlens);
        env.storage().instance().set(&DataKey::GateThreshold, &gate_threshold);
        env.storage().instance().set(&DataKey::MinConfidence, &min_confidence);
    }

    /// Gate liquidity provision on `query_risk_gate_with_confidence` **before**
    /// any pool state is mutated.
    pub fn provide_liquidity_gated(
        env: Env,
        provider: Address,
        amount: i128,
    ) -> Result<(), AmmLiquidityError> {
        if amount <= 0 {
            return Err(AmmLiquidityError::InvalidAmount);
        }

        let llens: Address = env
            .storage()
            .instance()
            .get(&DataKey::LedgerLens)
            .ok_or(AmmLiquidityError::NotConfigured)?;
        let threshold: u32 = env
            .storage()
            .instance()
            .get(&DataKey::GateThreshold)
            .ok_or(AmmLiquidityError::NotConfigured)?;
        let min_confidence: u32 = env
            .storage()
            .instance()
            .get(&DataKey::MinConfidence)
            .unwrap_or(0);

        let client = LedgerLensScoreContractClient::new(&env, &llens);
        let pair = symbol_short!("XLM_USDC");

        if !client.query_risk_gate_with_confidence(&provider, &pair, &threshold, &min_confidence) {
            match client.try_get_score(&provider, &pair) {
                Ok(Ok(score)) if score.confidence < min_confidence => {
                    return Err(AmmLiquidityError::LowConfidence);
                }
                _ => return Err(AmmLiquidityError::HighRiskProvider),
            }
        }

        // ... mint LP tokens / update reserves here ...
        Ok(())
    }
}
