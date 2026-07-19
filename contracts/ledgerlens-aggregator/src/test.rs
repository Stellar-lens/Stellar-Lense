#![cfg(test)]

use crate::{LedgerLensAggregator, LedgerLensAggregatorClient};
use ledgerlens_score::{Error, LedgerLensScoreContract, LedgerLensScoreContractClient};
use soroban_sdk::{symbol_short, testutils::Address as _, Address, Env};

fn register_score_shard<'a>(
    env: &Env,
    admin: &Address,
    service: &Address,
) -> (Address, LedgerLensScoreContractClient<'a>) {
    let shard_id = env.register_contract(None, LedgerLensScoreContract);
    let shard_client = LedgerLensScoreContractClient::new(env, &shard_id);
    shard_client.initialize(admin, service);
    (shard_id, shard_client)
}

#[test]
fn test_query_risk_gate_no_shards_returns_false() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    assert!(!client.query_risk_gate(&wallet, &pair, &75));
}

#[test]
fn test_get_decay_rate() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    let (shard_id, shard_client) = register_score_shard(&env, &admin, &service);

    client.initialize(&admin);
    client.add_shard(&shard_id);
    shard_client.set_decay_rate(&1, &1000);

    let (numerator, denominator) = client.get_decay_rate();

    assert_eq!(numerator, 1);
    assert_eq!(denominator, 1000);
    assert!(numerator < denominator, "Decay rate should be < 1.0");
}

#[test]
fn test_get_decay_rate_returns_primary_shard_when_shards_diverge() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    let (primary_id, primary_client) = register_score_shard(&env, &admin, &service);
    let (secondary_id, secondary_client) = register_score_shard(&env, &admin, &service);

    client.initialize(&admin);
    client.add_shard(&primary_id);
    client.add_shard(&secondary_id);
    primary_client.set_decay_rate(&1, &1000);
    secondary_client.set_decay_rate(&1, &500);

    assert_eq!(client.get_decay_rate(), (1, 1000));
}

#[test]
fn test_get_decay_rate_no_shards_returns_error() {
    let env = Env::default();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);

    assert_eq!(client.try_get_decay_rate(), Err(Ok(Error::ScoreNotFound)));
}

#[test]
fn test_get_consensus_threshold_k() {
    let env = Env::default();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);

    let k = client.get_consensus_threshold_k();

    assert_eq!(k, 5, "Should return the configured consensus threshold K");
    assert!(k >= 3, "K should be at least 3 for meaningful consensus");
}

#[test]
fn test_get_watchlist_status() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    let (shard_id, shard_client) = register_score_shard(&env, &admin, &service);

    client.initialize(&admin);
    client.add_shard(&shard_id);

    let wallet = Address::generate(&env);
    shard_client.set_watchlist(&soroban_sdk::Vec::new(&env), &wallet, &true);

    assert!(client.get_watchlist_status(&wallet));
}

#[test]
fn test_get_watchlist_status_returns_false_when_watchlisted_nowhere() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    let (shard_a_id, _) = register_score_shard(&env, &admin, &service);
    let (shard_b_id, _) = register_score_shard(&env, &admin, &service);

    client.initialize(&admin);
    client.add_shard(&shard_a_id);
    client.add_shard(&shard_b_id);

    let wallet = Address::generate(&env);

    assert!(!client.get_watchlist_status(&wallet));
}

#[test]
fn test_get_watchlist_status_returns_true_when_any_shard_watchlists_wallet() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    let (shard_a_id, _) = register_score_shard(&env, &admin, &service);
    let (shard_b_id, shard_b_client) = register_score_shard(&env, &admin, &service);

    client.initialize(&admin);
    client.add_shard(&shard_a_id);
    client.add_shard(&shard_b_id);

    let wallet = Address::generate(&env);
    shard_b_client.set_watchlist(&soroban_sdk::Vec::new(&env), &wallet, &true);

    assert!(client.get_watchlist_status(&wallet));
}

#[test]
fn test_get_watchlist_status_returns_true_when_all_shards_watchlist_wallet() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    let (shard_a_id, shard_a_client) = register_score_shard(&env, &admin, &service);
    let (shard_b_id, shard_b_client) = register_score_shard(&env, &admin, &service);

    client.initialize(&admin);
    client.add_shard(&shard_a_id);
    client.add_shard(&shard_b_id);

    let wallet = Address::generate(&env);
    shard_a_client.set_watchlist(&soroban_sdk::Vec::new(&env), &wallet, &true);
    shard_b_client.set_watchlist(&soroban_sdk::Vec::new(&env), &wallet, &true);

    assert!(client.get_watchlist_status(&wallet));
}
