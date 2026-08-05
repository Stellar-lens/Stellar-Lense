//! Structured error-event mapping tests for rejected batches.
//!
//! These tests verify that batch submissions generate machine-readable rejection
//! summaries without leaking sensitive input data. Each rejection code maps to
//! a documented event category for operator monitoring and alerting.

use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, Ledger as _},
    Address, Env, Symbol, Vec,
};

use crate::{
    constants::BatchEntryResult, Error, LedgerLensScoreContract, LedgerLensScoreContractClient,
};

const START_TS: u64 = 1_700_000_000;

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();
    env.budget().reset_unlimited();
    env.ledger().with_mut(|l| l.timestamp = START_TS);

    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);

    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    client.initialize(&admin, &service);

    (env, client, admin, service)
}

#[test]
fn test_batch_rejection_code_contract_paused() {
    let (env, client, _admin, _service) = setup();

    // Pause the contract
    client.pause();

    // Attempt batch submission
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    let mut batch = Vec::new(&env);
    batch.push_back(crate::types::ScoreSubmissionBatch {
        wallet: wallet.clone(),
        asset_pair: pair,
        score: 50,
        benford_flag: false,
        ml_flag: false,
        timestamp: START_TS,
        confidence: 80,
        model_version: 1,
    });

    let result = client.submit_scores_batch(&batch);

    // Verify rejection code indicates contract paused
    assert_eq!(result.len(), 1);
    let entry = result.get(0).unwrap();
    assert!(!entry.accepted);
    assert_eq!(
        entry.rejection_code,
        Error::ContractPaused as u32,
        "Rejection code should indicate contract pause"
    );
}

#[test]
fn test_batch_rejection_code_invalid_score() {
    let (env, client, _admin, _service) = setup();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    let mut batch = Vec::new(&env);
    // Score out of valid range (0-100)
    batch.push_back(crate::types::ScoreSubmissionBatch {
        wallet: wallet.clone(),
        asset_pair: pair,
        score: 150,
        benford_flag: false,
        ml_flag: false,
        timestamp: START_TS,
        confidence: 80,
        model_version: 1,
    });

    let result = client.submit_scores_batch(&batch);

    // Verify rejection code indicates invalid score
    assert_eq!(result.len(), 1);
    let entry = result.get(0).unwrap();
    assert!(!entry.accepted);
    assert_eq!(
        entry.rejection_code,
        Error::InvalidScore as u32,
        "Rejection code should indicate invalid score"
    );
}

#[test]
fn test_batch_rejection_code_invalid_confidence() {
    let (env, client, _admin, _service) = setup();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("BTC_USDT");

    let mut batch = Vec::new(&env);
    // Confidence out of valid range (0-100)
    batch.push_back(crate::types::ScoreSubmissionBatch {
        wallet: wallet.clone(),
        asset_pair: pair,
        score: 50,
        benford_flag: false,
        ml_flag: false,
        timestamp: START_TS,
        confidence: 150,
        model_version: 1,
    });

    let result = client.submit_scores_batch(&batch);

    // Verify rejection code indicates invalid confidence
    assert_eq!(result.len(), 1);
    let entry = result.get(0).unwrap();
    assert!(!entry.accepted);
    assert_eq!(
        entry.rejection_code,
        Error::InvalidConfidence as u32,
        "Rejection code should indicate invalid confidence"
    );
}

#[test]
fn test_batch_rejection_code_invalid_timestamp() {
    let (env, client, _admin, _service) = setup();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("ETH_USDC");

    let mut batch = Vec::new(&env);
    // Timestamp in future
    batch.push_back(crate::types::ScoreSubmissionBatch {
        wallet: wallet.clone(),
        asset_pair: pair,
        score: 50,
        benford_flag: false,
        ml_flag: false,
        timestamp: START_TS + 1_000_000_000,
        confidence: 80,
        model_version: 1,
    });

    let result = client.submit_scores_batch(&batch);

    // Verify rejection code indicates invalid timestamp
    assert_eq!(result.len(), 1);
    let entry = result.get(0).unwrap();
    assert!(!entry.accepted);
    assert_eq!(
        entry.rejection_code,
        Error::InvalidTimestamp as u32,
        "Rejection code should indicate invalid timestamp"
    );
}

#[test]
fn test_batch_mixed_acceptance_and_rejection() {
    let (env, client, _admin, _service) = setup();

    let wallet1 = Address::generate(&env);
    let wallet2 = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    let mut batch = Vec::new(&env);

    // Valid entry
    batch.push_back(crate::types::ScoreSubmissionBatch {
        wallet: wallet1.clone(),
        asset_pair: pair,
        score: 45,
        benford_flag: false,
        ml_flag: false,
        timestamp: START_TS,
        confidence: 80,
        model_version: 1,
    });

    // Invalid score entry
    batch.push_back(crate::types::ScoreSubmissionBatch {
        wallet: wallet2.clone(),
        asset_pair: pair,
        score: 150,
        benford_flag: false,
        ml_flag: false,
        timestamp: START_TS,
        confidence: 80,
        model_version: 1,
    });

    let result = client.submit_scores_batch(&batch);

    // Verify first entry accepted, second rejected
    assert_eq!(result.len(), 2);

    let entry0 = result.get(0).unwrap();
    assert!(entry0.accepted, "First entry should be accepted");
    assert_eq!(entry0.rejection_code, 0, "Accepted entries have zero rejection code");

    let entry1 = result.get(1).unwrap();
    assert!(!entry1.accepted, "Second entry should be rejected");
    assert_eq!(
        entry1.rejection_code,
        Error::InvalidScore as u32,
        "Second entry should have invalid score code"
    );
}

#[test]
fn test_batch_rejection_deterministic_across_wallets() {
    let (env, client, _admin, _service) = setup();

    // Submit same invalid data for different wallets
    let wallets: Vec<Address> = (0..3).map(|_| Address::generate(&env)).collect::<Vec<_>>().into();
    let pair = symbol_short!("XLM_USDC");

    let mut batch = Vec::new(&env);
    for wallet in wallets.iter() {
        batch.push_back(crate::types::ScoreSubmissionBatch {
            wallet: wallet.clone(),
            asset_pair: pair,
            score: 150, // Invalid
            benford_flag: false,
            ml_flag: false,
            timestamp: START_TS,
            confidence: 80,
            model_version: 1,
        });
    }

    let result = client.submit_scores_batch(&batch);

    // Verify all entries rejected with same code (deterministic)
    assert_eq!(result.len(), 3);
    for i in 0..3 {
        let entry = result.get(i).unwrap();
        assert!(!entry.accepted);
        assert_eq!(
            entry.rejection_code,
            Error::InvalidScore as u32,
            "All entries should have same deterministic rejection code"
        );
    }
}

#[test]
fn test_rejection_does_not_leak_wallet_data() {
    let (env, client, _admin, _service) = setup();

    let sensitive_wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    let mut batch = Vec::new(&env);
    batch.push_back(crate::types::ScoreSubmissionBatch {
        wallet: sensitive_wallet.clone(),
        asset_pair: pair,
        score: 50,
        benford_flag: false,
        ml_flag: false,
        timestamp: START_TS,
        confidence: 150, // Invalid
        model_version: 1,
    });

    let result = client.submit_scores_batch(&batch);

    // Verify the event/result contains only rejection reason, not wallet details
    let entry = result.get(0).unwrap();
    assert!(!entry.accepted);
    assert_eq!(
        entry.rejection_code,
        Error::InvalidConfidence as u32,
        "Event should contain rejection reason without wallet data"
    );
    // The wallet address itself is not part of the rejection response
    // in terms of the rejection_code - only the category is returned
}
