#![cfg(test)]

use crate::{LedgerLensAggregator, LedgerLensAggregatorClient};
use ledgerlens_score::{LedgerLensScoreContract, LedgerLensScoreContractClient};
use soroban_sdk::{symbol_short, testutils::Address as _, Address, Env};

fn setup_score<'a>(env: &'a Env, admin: &Address, service: &Address) -> (Address, LedgerLensScoreContractClient<'a>) {
    let id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(env, &id);
    client.initialize(admin, service);
    (id, client)
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
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);

    let (numerator, denominator) = client.get_decay_rate();

    assert_eq!(numerator, 999);
    assert_eq!(denominator, 1000);
    assert!(numerator < denominator, "Decay rate should be < 1.0");
}

#[test]
fn test_get_consensus_threshold_k_default() {
    let env = Env::default();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);

    // No shards registered — must return default K (2)
    assert_eq!(client.get_consensus_threshold_k(), 2);
}

#[test]
fn test_get_consensus_threshold_k_with_shard_default_k() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    let (shard_id, _) = setup_score(&env, &admin, &service);

    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let agg_client = LedgerLensAggregatorClient::new(&env, &agg_id);
    agg_client.initialize(&admin);
    agg_client.add_shard(&shard_id);

    // Score contract default K is 2
    assert_eq!(agg_client.get_consensus_threshold_k(), 2);
}

#[test]
fn test_get_consensus_threshold_k_single_shard_custom() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    let (shard_id, shard_client) = setup_score(&env, &admin, &service);

    shard_client.set_consensus_config(&7, &10);

    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let agg_client = LedgerLensAggregatorClient::new(&env, &agg_id);
    agg_client.initialize(&admin);
    agg_client.add_shard(&shard_id);

    assert_eq!(agg_client.get_consensus_threshold_k(), 7);
}

#[test]
fn test_get_consensus_threshold_k_uses_min_across_shards() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let service = Address::generate(&env);

    let (shard1_id, shard1_client) = setup_score(&env, &admin, &service);
    shard1_client.set_consensus_config(&3, &5);

    let (shard2_id, shard2_client) = setup_score(&env, &admin, &service);
    shard2_client.set_consensus_config(&7, &5);

    let (shard3_id, shard3_client) = setup_score(&env, &admin, &service);
    shard3_client.set_consensus_config(&5, &5);

    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let agg_client = LedgerLensAggregatorClient::new(&env, &agg_id);
    agg_client.initialize(&admin);
    agg_client.add_shard(&shard1_id);
    agg_client.add_shard(&shard2_id);
    agg_client.add_shard(&shard3_id);

    // Min K across shards = 3
    assert_eq!(agg_client.get_consensus_threshold_k(), 3);
}

#[test]
fn test_get_watchlist_status() {
    let env = Env::default();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);

    let unwatched_wallet = Address::generate(&env);

    // Test unwatched (default)
    assert!(!client.get_watchlist_status(&unwatched_wallet));
}
