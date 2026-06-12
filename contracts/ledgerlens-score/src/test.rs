#![cfg(test)]

use soroban_sdk::{symbol_short, testutils::Address as _, Address, Env};

use crate::{Error, LedgerLensScoreContract, LedgerLensScoreContractClient};

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();

    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);

    let admin = Address::generate(&env);
    let service = Address::generate(&env);

    (env, client, admin, service)
}

#[test]
fn test_initialize() {
    let (_env, client, admin, service) = setup();

    client.initialize(&admin, &service);

    assert_eq!(client.get_admin(), admin);
    assert_eq!(client.get_service(), service);
}

#[test]
fn test_initialize_twice_fails() {
    let (_env, client, admin, service) = setup();

    client.initialize(&admin, &service);
    let result = client.try_initialize(&admin, &service);

    assert_eq!(result, Err(Ok(Error::AlreadyInitialized)));
}

#[test]
fn test_submit_and_get_score() {
    let (env, client, admin, service) = setup();
    client.initialize(&admin, &service);

    let wallet = Address::generate(&env);
    let asset_pair = symbol_short!("XLM_USDC");

    client.submit_score(&wallet, &asset_pair, &87, &true, &true, &1_700_000_000, &92);

    let score = client.get_score(&wallet, &asset_pair);
    assert_eq!(score.score, 87);
    assert!(score.benford_flag);
    assert!(score.ml_flag);
    assert_eq!(score.timestamp, 1_700_000_000);
    assert_eq!(score.confidence, 92);
}

#[test]
fn test_get_score_not_found() {
    let (env, client, admin, service) = setup();
    client.initialize(&admin, &service);

    let wallet = Address::generate(&env);
    let asset_pair = symbol_short!("XLM_USDC");

    let result = client.try_get_score(&wallet, &asset_pair);
    assert_eq!(result, Err(Ok(Error::ScoreNotFound)));
}

#[test]
fn test_submit_score_invalid_range_rejected() {
    let (env, client, admin, service) = setup();
    client.initialize(&admin, &service);

    let wallet = Address::generate(&env);
    let asset_pair = symbol_short!("XLM_USDC");

    let result = client.try_submit_score(&wallet, &asset_pair, &101, &false, &false, &0, &50);
    assert_eq!(result, Err(Ok(Error::InvalidScore)));

    let result = client.try_submit_score(&wallet, &asset_pair, &50, &false, &false, &0, &101);
    assert_eq!(result, Err(Ok(Error::InvalidConfidence)));
}

#[test]
fn test_set_service_rotates_authorised_account() {
    let (env, client, admin, service) = setup();
    client.initialize(&admin, &service);

    let new_service = Address::generate(&env);
    client.set_service(&new_service);

    assert_eq!(client.get_service(), new_service);

    // Old service can no longer submit scores once mock auth is scoped
    // to the new account in a non-mocked environment; here we just
    // confirm the new service is recorded.
    let wallet = Address::generate(&env);
    let asset_pair = symbol_short!("XLM_USDC");
    client.submit_score(&wallet, &asset_pair, &10, &false, &false, &0, &10);
}
