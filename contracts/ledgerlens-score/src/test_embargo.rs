//! Tests for the per-wallet score embargo (regulatory hold).
//! Issue #50: Block Score Reads for Investigation-Tagged Wallets Without Deleting Data.

use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, Ledger as _},
    Address, Env, Vec,
};

use crate::{Error, LedgerLensScoreContract, LedgerLensScoreContractClient};

const START_TS: u64 = 1_700_000_000;

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();
    env.ledger().with_mut(|l| l.timestamp = START_TS);

    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);

    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    client.initialize(&admin, &service);

    (env, client, admin, service)
}

fn submit(
    env: &Env,
    client: &LedgerLensScoreContractClient,
    wallet: &Address,
    pair: &soroban_sdk::Symbol,
    score: u32,
) {
    client.submit_score(
        &Vec::new(env),
        wallet,
        pair,
        &score,
        &false,
        &false,
        &START_TS,
        &90,
        &1,
        &None,
    );
}

// ── is_embargoed baseline ────────────────────────────────────────────────────

#[test]
fn test_embargo_not_set_returns_false() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    assert!(!client.is_embargoed(&wallet));
}

// ── set_score_embargo / is_embargoed ────────────────────────────────────────

#[test]
fn test_embargo_indefinite_is_active() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    client.set_score_embargo(&wallet, &None);
    assert!(client.is_embargoed(&wallet));
}

#[test]
fn test_embargo_future_expiry_is_active() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    let future = START_TS + 3_600;
    client.set_score_embargo(&wallet, &Some(future));
    assert!(client.is_embargoed(&wallet));
}

// ── get_score blocked ───────────────────────────────────────────────────────

#[test]
fn test_embargo_blocks_get_score() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    submit(&env, &client, &wallet, &pair, 50);
    assert_eq!(client.get_score(&wallet, &pair).score, 50);

    client.set_score_embargo(&wallet, &None);

    let result = client.try_get_score(&wallet, &pair);
    assert_eq!(result, Err(Ok(Error::ScoreEmbargoed)));
}

// ── submit_score still succeeds under embargo ────────────────────────────────

#[test]
fn test_embargo_allows_submit_score() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    client.set_score_embargo(&wallet, &None);

    // Writes must still succeed — the embargo only blocks reads.
    let result = client.try_submit_score(
        &Vec::new(&env),
        &wallet,
        &pair,
        &75,
        &true,
        &false,
        &START_TS,
        &80,
        &1,
        &None,
    );
    assert_eq!(result, Ok(Ok(())));
}

// ── query_risk_gate returns false ────────────────────────────────────────────

#[test]
fn test_embargo_query_risk_gate_returns_false() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    // Score is 10 — well below threshold 75; gate normally returns true.
    submit(&env, &client, &wallet, &pair, 10);
    assert!(client.query_risk_gate(&wallet, &pair, &75));

    client.set_score_embargo(&wallet, &None);
    assert!(!client.query_risk_gate(&wallet, &pair, &75));
}

// ── get_score_history returns empty Vec ──────────────────────────────────────

#[test]
fn test_embargo_history_returns_empty() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    submit(&env, &client, &wallet, &pair, 30);
    assert_eq!(client.get_score_history(&wallet, &pair).len(), 1);

    client.set_score_embargo(&wallet, &None);
    assert!(client.get_score_history(&wallet, &pair).is_empty());
}

// ── get_aggregate_score blocked ──────────────────────────────────────────────

#[test]
fn test_embargo_blocks_aggregate_score() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    submit(&env, &client, &wallet, &pair, 60);
    // Should succeed before embargo.
    client.get_aggregate_score(&wallet);

    client.set_score_embargo(&wallet, &None);

    let result = client.try_get_aggregate_score(&wallet);
    assert_eq!(result, Err(Ok(Error::ScoreEmbargoed)));
}

// ── Expiry auto-lift ─────────────────────────────────────────────────────────

#[test]
fn test_embargo_expiry_auto_lifts() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    let expiry = START_TS + 1_000;

    submit(&env, &client, &wallet, &pair, 42);

    client.set_score_embargo(&wallet, &Some(expiry));
    assert!(client.is_embargoed(&wallet));
    assert_eq!(client.try_get_score(&wallet, &pair), Err(Ok(Error::ScoreEmbargoed)));

    // Advance to the expiry timestamp — embargo should be auto-lifted.
    env.ledger().with_mut(|l| l.timestamp = expiry);
    assert!(!client.is_embargoed(&wallet));
    assert_eq!(client.get_score(&wallet, &pair).score, 42);
}

// ── Indefinite requires explicit lift ────────────────────────────────────────

#[test]
fn test_embargo_indefinite_requires_explicit_lift() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);

    client.set_score_embargo(&wallet, &None);
    assert!(client.is_embargoed(&wallet));

    // Advancing time far into the future must not lift an indefinite embargo.
    env.ledger().with_mut(|l| l.timestamp = u64::MAX / 2);
    assert!(client.is_embargoed(&wallet));

    client.lift_score_embargo(&wallet);
    assert!(!client.is_embargoed(&wallet));
}

// ── Embargo is per-wallet ────────────────────────────────────────────────────

#[test]
fn test_embargo_does_not_affect_other_wallets() {
    let (env, client, _, _) = setup();
    let wallet_a = Address::generate(&env);
    let wallet_b = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    submit(&env, &client, &wallet_a, &pair, 55);
    submit(&env, &client, &wallet_b, &pair, 20);

    client.set_score_embargo(&wallet_a, &None);

    // wallet_a is blocked.
    assert_eq!(client.try_get_score(&wallet_a, &pair), Err(Ok(Error::ScoreEmbargoed)));
    // wallet_b is unaffected.
    assert_eq!(client.get_score(&wallet_b, &pair).score, 20);
}

// ── lift_score_embargo restores access ───────────────────────────────────────

#[test]
fn test_lift_embargo_restores_access() {
    let (env, client, _, _) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    submit(&env, &client, &wallet, &pair, 88);

    client.set_score_embargo(&wallet, &None);
    assert!(client.is_embargoed(&wallet));

    client.lift_score_embargo(&wallet);
    assert!(!client.is_embargoed(&wallet));
    assert_eq!(client.get_score(&wallet, &pair).score, 88);
}
