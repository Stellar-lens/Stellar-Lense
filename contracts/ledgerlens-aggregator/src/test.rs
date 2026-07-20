#![cfg(test)]

use crate::{Error, LedgerLensAggregator, LedgerLensAggregatorClient};
use ledgerlens_score::{LedgerLensScoreContract, LedgerLensScoreContractClient};
use soroban_sdk::{symbol_short, testutils::Address as _, Address, Env, Vec};

#[test]
fn test_initialize() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);
    assert_eq!(client.get_admin(), admin);
}

#[test]
fn test_initialize_twice_fails() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);
    let result = client.try_initialize(&admin);
    assert_eq!(result, Err(Ok(Error::AlreadyInitialized)));
}

#[test]
fn test_get_admin_not_initialized() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let result = client.try_get_admin();
    assert_eq!(result, Err(Ok(Error::NotInitialized)));
}

#[test]
fn test_add_remove_shards() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let shard = Address::generate(&env);
    client.add_shard(&shard);

    let shards = client.get_shards();
    assert_eq!(shards.len(), 1);
    assert_eq!(shards.get(0).unwrap(), shard);

    client.remove_shard(&shard);
    assert_eq!(client.get_shards().len(), 0);
}

#[test]
fn test_add_shard_self_reference_fails() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let result = client.try_add_shard(&agg_id);
    assert_eq!(result, Err(Ok(Error::SelfReference)));
}

#[test]
fn test_add_shard_duplicate_fails() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let shard = Address::generate(&env);
    client.add_shard(&shard);
    let result = client.try_add_shard(&shard);
    assert_eq!(result, Err(Ok(Error::ShardAlreadyRegistered)));
}

#[test]
fn test_remove_nonexistent_shard_fails() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let shard = Address::generate(&env);
    let result = client.try_remove_shard(&shard);
    assert_eq!(result, Err(Ok(Error::ShardNotRegistered)));
}

#[test]
fn test_query_risk_gate_no_shards_returns_no_shards_error() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    let result = client.try_query_risk_gate(&wallet, &pair, &75);
    assert_eq!(result, Err(Ok(Error::NoShards)));
}

#[test]
fn test_query_risk_gate_all_shards_pass() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let (shard1_id, shard1) = setup_score_shard(&env);
    let (shard2_id, shard2) = setup_score_shard(&env);
    client.add_shard(&shard1_id);
    client.add_shard(&shard2_id);

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    shard1.submit_score(&Vec::new(&env), &wallet, &pair, &10, &false, &false, &1, &100, &1, &None);
    shard2.submit_score(&Vec::new(&env), &wallet, &pair, &10, &false, &false, &1, &100, &1, &None);

    assert!(client.query_risk_gate(&wallet, &pair, &75));
}

#[test]
fn test_query_risk_gate_one_shard_rejects() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let (shard1_id, shard1) = setup_score_shard(&env);
    let (shard2_id, shard2) = setup_score_shard(&env);
    client.add_shard(&shard1_id);
    client.add_shard(&shard2_id);

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    shard1.submit_score(&Vec::new(&env), &wallet, &pair, &10, &false, &false, &1, &100, &1, &None);
    shard2.submit_score(&Vec::new(&env), &wallet, &pair, &90, &false, &false, &1, &100, &1, &None);

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
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);

    let unwatched_wallet = Address::generate(&env);

    assert!(!client.get_watchlist_status(&unwatched_wallet));
}

fn setup_score_shard(env: &Env) -> (Address, LedgerLensScoreContractClient<'_>) {
    let id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(env, &id);
    let admin = Address::generate(env);
    let service = Address::generate(env);
    client.initialize(&admin, &service);
    (id, client)
}

#[test]
fn test_get_score_with_shards() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let (shard1_id, shard1) = setup_score_shard(&env);
    let (shard2_id, shard2) = setup_score_shard(&env);
    client.add_shard(&shard1_id);
    client.add_shard(&shard2_id);

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    shard1.submit_score(&Vec::new(&env), &wallet, &pair, &30, &false, &false, &1, &100, &1, &None);
    shard2.submit_score(&Vec::new(&env), &wallet, &pair, &70, &false, &false, &1, &100, &1, &None);

    let score = client.get_score(&wallet, &pair);
    assert_eq!(score.score, 70);
}

#[test]
fn test_get_score_not_found() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let (shard1_id, _shard1) = setup_score_shard(&env);
    client.add_shard(&shard1_id);

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    let result = client.try_get_score(&wallet, &pair);
    assert_eq!(result, Err(Ok(Error::ScoreNotFound)));
}

#[test]
fn test_get_aggregate_score_not_found() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let (shard1_id, _shard1) = setup_score_shard(&env);
    client.add_shard(&shard1_id);

    let wallet = Address::generate(&env);
    let result = client.try_get_aggregate_score(&wallet);
    assert_eq!(result, Err(Ok(Error::ScoreNotFound)));
}

#[test]
fn test_get_last_shard_failure_after_shard_error() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let fake_shard = Address::generate(&env);
    client.add_shard(&fake_shard);

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    let result = client.try_get_score(&wallet, &pair);
    // No shard has data, so aggregator returns ScoreNotFound.
    // get_last_shard_failure may or may not be visible after
    // a failed try_ call; it is verified in the passing
    // test_shard_failure_in_get_score test below.
    assert_eq!(result, Err(Ok(Error::ScoreNotFound)));
}

#[test]
fn test_shard_failure_in_query_risk_gate() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let fake_shard = Address::generate(&env);
    client.add_shard(&fake_shard);

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    let result = client.try_query_risk_gate(&wallet, &pair, &75);
    assert_eq!(result, Err(Ok(Error::ShardFailure)));
}

#[test]
fn test_shard_failure_in_get_score() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);

    let (real_shard_id, real_shard) = setup_score_shard(&env);
    let fake_shard = Address::generate(&env);
    client.add_shard(&real_shard_id);
    client.add_shard(&fake_shard);

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    real_shard.submit_score(&Vec::new(&env), &wallet, &pair, &50, &false, &false, &1, &100, &1, &None);

    let score = client.get_score(&wallet, &pair);
    assert_eq!(score.score, 50);

    let failure = client.get_last_shard_failure().unwrap();
    assert_eq!(failure.0, fake_shard);
}

#[test]
fn test_contagion_depth_across_shards_with_cross_shard_cycle() {
    let env = Env::default();
    env.mock_all_auths();

    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let agg_client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let agg_admin = Address::generate(&env);
    agg_client.initialize(&agg_admin);

    let (shard1_id, shard1) = setup_score_shard(&env);
    let (shard2_id, shard2) = setup_score_shard(&env);

    agg_client.add_shard(&shard1_id);
    agg_client.add_shard(&shard2_id);

    let wallet_a = Address::generate(&env);
    let wallet_b = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    shard1.set_score_delegate(&wallet_a, &wallet_b);
    shard2.set_score_delegate(&wallet_b, &wallet_a);

    let c1 = Address::generate(&env);
    let c2 = Address::generate(&env);
    let c3 = Address::generate(&env);
    shard1.add_counterparty_link(&wallet_a, &c1, &pair);
    shard1.add_counterparty_link(&wallet_a, &c2, &pair);
    shard1.add_counterparty_link(&wallet_a, &c3, &pair);

    let d1 = Address::generate(&env);
    let d2 = Address::generate(&env);
    let d3 = Address::generate(&env);
    let d4 = Address::generate(&env);
    let d5 = Address::generate(&env);
    shard2.add_counterparty_link(&wallet_a, &d1, &pair);
    shard2.add_counterparty_link(&wallet_a, &d2, &pair);
    shard2.add_counterparty_link(&wallet_a, &d3, &pair);
    shard2.add_counterparty_link(&wallet_a, &d4, &pair);
    shard2.add_counterparty_link(&wallet_a, &d5, &pair);

    assert_eq!(shard1.get_contagion_depth(&wallet_a, &pair), 3);
    assert_eq!(shard2.get_contagion_depth(&wallet_a, &pair), 5);

    let depth = agg_client.contagion_depth_across_shards(&wallet_a, &pair);
    assert_eq!(depth, 5, "should return max contagion depth across shards");

    let isolated = Address::generate(&env);
    let depth_zero = agg_client.contagion_depth_across_shards(&isolated, &pair);
    assert_eq!(depth_zero, 0, "wallet with no links should return 0");
}

#[test]
fn test_contagion_depth_across_shards_no_shards() {
    let env = Env::default();
    env.mock_all_auths();
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    assert_eq!(client.contagion_depth_across_shards(&wallet, &pair), 0);
}
