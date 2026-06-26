use ledgerlens_score::{LedgerLensScoreContract, LedgerLensScoreContractClient};
use soroban_sdk::{
    testutils::{Address as _, Ledger as _},
    symbol_short,
    Address, Env, Vec,
};

use crate::{MockAmm, MockAmmClient, MockAmmError};

const GATE_THRESHOLD: u32 = 75;
const MIN_CONFIDENCE: u32 = 50;

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, MockAmmClient<'a>, Address) {
    let env = Env::default();
    env.mock_all_auths();
    env.ledger().with_mut(|l| l.timestamp = 1_700_000_000);

    let ledgerlens_id = env.register_contract(None, LedgerLensScoreContract);
    let ledgerlens = LedgerLensScoreContractClient::new(&env, &ledgerlens_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    ledgerlens.initialize(&admin, &service);

    let amm_id = env.register_contract(None, MockAmm);
    let amm = MockAmmClient::new(&env, &amm_id);
    amm.initialize(&ledgerlens_id, &GATE_THRESHOLD);
    amm.set_liquidity_gate_config(&GATE_THRESHOLD, &MIN_CONFIDENCE);

    (env, ledgerlens, amm, service)
}

fn submit_score(
    env: &Env,
    ledgerlens: &LedgerLensScoreContractClient,
    service: &Address,
    wallet: &Address,
    score: u32,
    confidence: u32,
) {
    ledgerlens.submit_score(
        &Vec::from_array(env, [service.clone()]),
        wallet,
        &symbol_short!("XLM_USDC"),
        &score,
        &false,
        &false,
        &1_700_000_000u64,
        &confidence,
        &1u32,
        &None,
    );
}

#[test]
fn provide_liquidity_allowed_for_low_risk_high_confidence() {
    let (env, ledgerlens, amm, service) = setup();
    let provider = Address::generate(&env);
    submit_score(&env, &ledgerlens, &service, &provider, 10, 90);

    assert_eq!(amm.try_provide_liquidity_gated(&provider, &1_000), Ok(Ok(())));
}

#[test]
fn provide_liquidity_blocked_for_high_risk_provider() {
    let (env, ledgerlens, amm, service) = setup();
    let provider = Address::generate(&env);
    submit_score(&env, &ledgerlens, &service, &provider, 90, 95);

    let result = amm.try_provide_liquidity_gated(&provider, &1_000);
    assert_eq!(result, Err(Ok(MockAmmError::HighRiskWallet)));
}

#[test]
fn provide_liquidity_blocked_for_low_confidence() {
    let (env, ledgerlens, amm, service) = setup();
    let provider = Address::generate(&env);
    submit_score(&env, &ledgerlens, &service, &provider, 10, 20);

    let result = amm.try_provide_liquidity_gated(&provider, &1_000);
    assert_eq!(result, Err(Ok(MockAmmError::LowConfidence)));
}

#[test]
fn provide_liquidity_uses_risk_oracle_from_set_risk_oracle() {
    let env = Env::default();
    env.mock_all_auths();
    env.ledger().with_mut(|l| l.timestamp = 1_700_000_000);

    let oracle_a = env.register_contract(None, LedgerLensScoreContract);
    let oracle_b = env.register_contract(None, LedgerLensScoreContract);
    let client_a = LedgerLensScoreContractClient::new(&env, &oracle_a);
    let client_b = LedgerLensScoreContractClient::new(&env, &oracle_b);

    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    client_a.initialize(&admin, &service);
    client_b.initialize(&admin, &service);

    let amm_id = env.register_contract(None, MockAmm);
    let amm = MockAmmClient::new(&env, &amm_id);
    amm.initialize(&oracle_a, &GATE_THRESHOLD);
    amm.set_liquidity_gate_config(&GATE_THRESHOLD, &MIN_CONFIDENCE);

    let provider = Address::generate(&env);
    // Safe on oracle B, risky on oracle A (the one wired via set_risk_oracle).
    submit_score(&env, &client_b, &service, &provider, 10, 90);
    submit_score(&env, &client_a, &service, &provider, 90, 95);

    amm.set_risk_oracle(&oracle_b);

    assert_eq!(amm.try_provide_liquidity_gated(&provider, &500), Ok(Ok(())));
}
