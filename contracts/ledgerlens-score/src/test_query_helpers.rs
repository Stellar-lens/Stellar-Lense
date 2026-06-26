#![cfg(test)]

use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, Ledger as _},
    Address, Env, Vec,
};

use crate::{
    LedgerLensScoreContract, LedgerLensScoreContractClient,
};

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();

    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);

    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    client.initialize(&admin, &service);

    (env, client, admin, service)
}

// ─────────────────────────────────────────────────────────────────────────────
// Issue #100 – get_score_age
// ─────────────────────────────────────────────────────────────────────────────

#[test]
fn test_get_score_age_no_score_returns_zero() {
    let (env, client, _admin, _service) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    // No score has ever been submitted → age is 0.
    assert_eq!(client.get_score_age(&wallet, &pair), 0);
}

#[test]
fn test_get_score_age_just_submitted() {
    // Ledger timestamp is 1_000_000 at submission, no time advances → age = 0.
    let (env, client, _admin, _service) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    env.ledger().with_mut(|l| l.timestamp = 1_000_000);

    client.submit_score(
        &Vec::new(&env),
        &wallet,
        &pair,
        &40,
        &false,
        &false,
        &1_700_000_000,
        &90,
        &1,
        &None,
    );

    // Time has not advanced → age should be 0.
    assert_eq!(client.get_score_age(&wallet, &pair), 0);
}

#[test]
fn test_get_score_age_after_time_advance() {
    let (env, client, _admin, _service) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    env.ledger().with_mut(|l| l.timestamp = 1_000_000);

    client.submit_score(
        &Vec::new(&env),
        &wallet,
        &pair,
        &40,
        &false,
        &false,
        &1_700_000_000,
        &90,
        &1,
        &None,
    );

    // Advance ledger by 7200 seconds (2 hours).
    env.ledger().with_mut(|l| l.timestamp = 1_007_200);

    assert_eq!(client.get_score_age(&wallet, &pair), 7200);
}

#[test]
fn test_get_score_age_unknown_pair_returns_zero() {
    let (env, client, _admin, _service) = setup();
    let wallet = Address::generate(&env);
    let scored_pair = symbol_short!("XLM_USDC");
    let other_pair = symbol_short!("BTC_USDC");

    env.ledger().with_mut(|l| l.timestamp = 1_000_000);

    // Submit for scored_pair only.
    client.submit_score(
        &Vec::new(&env),
        &wallet,
        &scored_pair,
        &40,
        &false,
        &false,
        &1_700_000_000,
        &90,
        &1,
        &None,
    );

    // other_pair was never scored → age is 0.
    assert_eq!(client.get_score_age(&wallet, &other_pair), 0);
}

// ─────────────────────────────────────────────────────────────────────────────
// Issue #246 – get_counterparty_list
// ─────────────────────────────────────────────────────────────────────────────

#[test]
fn test_get_counterparty_list_empty_when_no_links() {
    let (env, client, _admin, _service) = setup();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    // No links recorded → empty list.
    assert_eq!(client.get_counterparty_list(&wallet, &pair), Vec::new(&env));
}

#[test]
fn test_get_counterparty_list_returns_bidirectional_links() {
    let (env, client, _admin, _service) = setup();
    let alice = Address::generate(&env);
    let bob = Address::generate(&env);
    let carol = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    client.add_counterparty_link(&alice, &bob, &pair);
    client.add_counterparty_link(&alice, &carol, &pair);

    // Alice is linked to both bob and carol.
    let alice_links = client.get_counterparty_list(&alice, &pair);
    assert_eq!(alice_links.len(), 2);
    assert!(alice_links.contains(&bob));
    assert!(alice_links.contains(&carol));

    // Links are bidirectional: bob and carol each list alice back.
    assert_eq!(client.get_counterparty_list(&bob, &pair), Vec::from_array(&env, [alice.clone()]));
    assert_eq!(client.get_counterparty_list(&carol, &pair), Vec::from_array(&env, [alice]));
}
