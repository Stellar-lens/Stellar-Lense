#![cfg(test)]

use crate::{LedgerLensAggregator, LedgerLensAggregatorClient};
use ledgerlens_score::{Error as ScoreError, LedgerLensScoreContract};
use soroban_sdk::{symbol_short, testutils::Address as _, Address, Env};

/// A shard whose interface has fully drifted: it advertises no capability the
/// aggregator depends on.
mod incompatible_shard {
    use soroban_sdk::{contract, contractimpl, Env, Symbol};

    #[contract]
    pub struct IncompatibleShard;

    #[contractimpl]
    impl IncompatibleShard {
        pub fn supports_interface(_env: Env, _capability: Symbol) -> bool {
            false
        }
    }
}

/// A shard that implements part of the interface (`score`, `gate`) but is
/// missing the `aggr` capability the aggregator also invokes.
mod partial_shard {
    use soroban_sdk::{contract, contractimpl, Env, Symbol};

    #[contract]
    pub struct PartialShard;

    #[contractimpl]
    impl PartialShard {
        pub fn supports_interface(env: Env, capability: Symbol) -> bool {
            capability == Symbol::new(&env, "score") || capability == Symbol::new(&env, "gate")
        }
    }
}

/// A shard that predates the capability-detection interface entirely: it does
/// not expose `supports_interface`, so the cross-contract call traps.
mod legacy_shard {
    use soroban_sdk::{contract, contractimpl, Env};

    #[contract]
    pub struct LegacyShard;

    #[contractimpl]
    impl LegacyShard {
        pub fn ping(_env: Env) -> bool {
            true
        }
    }
}

fn init_aggregator(env: &Env) -> LedgerLensAggregatorClient<'_> {
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let client = LedgerLensAggregatorClient::new(env, &agg_id);
    client.initialize(&Address::generate(env));
    client
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

#[test]
fn test_add_shard_accepts_compatible_score_contract() {
    let env = Env::default();
    env.mock_all_auths();
    let client = init_aggregator(&env);

    let shard = env.register_contract(None, LedgerLensScoreContract);
    client.add_shard(&shard);

    let shards = client.get_shards();
    assert_eq!(shards.len(), 1);
    assert_eq!(shards.get(0).unwrap(), shard);
}

#[test]
fn test_add_shard_rejects_incompatible_shard() {
    let env = Env::default();
    env.mock_all_auths();
    let client = init_aggregator(&env);

    let shard = env.register_contract(None, incompatible_shard::IncompatibleShard);
    let result = client.try_add_shard(&shard);

    assert_eq!(result, Err(Ok(ScoreError::IncompatibleInterface)));
    assert_eq!(client.get_shards().len(), 0);
}

#[test]
fn test_add_shard_rejects_shard_missing_capability() {
    let env = Env::default();
    env.mock_all_auths();
    let client = init_aggregator(&env);

    let shard = env.register_contract(None, partial_shard::PartialShard);
    let result = client.try_add_shard(&shard);

    assert_eq!(result, Err(Ok(ScoreError::IncompatibleInterface)));
    assert_eq!(client.get_shards().len(), 0);
}

#[test]
fn test_add_shard_rejects_legacy_shard_without_supports_interface() {
    let env = Env::default();
    env.mock_all_auths();
    let client = init_aggregator(&env);

    let shard = env.register_contract(None, legacy_shard::LegacyShard);
    let result = client.try_add_shard(&shard);

    assert_eq!(result, Err(Ok(ScoreError::IncompatibleInterface)));
    assert_eq!(client.get_shards().len(), 0);
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
fn test_contagion_depth_across_shards_with_cross_shard_cycle() {
    let env = Env::default();
    env.mock_all_auths();

    // Register aggregator
    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let agg_client = LedgerLensAggregatorClient::new(&env, &agg_id);
    let agg_admin = Address::generate(&env);
    agg_client.initialize(&agg_admin);

    // Register two score shards
    let (shard1_id, shard1) = setup_score_shard(&env);
    let (shard2_id, shard2) = setup_score_shard(&env);

    // Add shards to aggregator
    agg_client.add_shard(&shard1_id);
    agg_client.add_shard(&shard2_id);

    let wallet_a = Address::generate(&env);
    let wallet_b = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    // Create a cross-shard cyclic delegation:
    //   Shard 1: wallet_a delegates to wallet_b
    //   Shard 2: wallet_b delegates back to wallet_a
    // This forms a cycle no single-shard cycle detector can see.
    shard1.set_score_delegate(&wallet_a, &wallet_b);
    shard2.set_score_delegate(&wallet_b, &wallet_a);

    // Add counterparty links to give non-zero contagion depth on each shard.
    // Shard 1: wallet_a has 3 counterparties.
    let c1 = Address::generate(&env);
    let c2 = Address::generate(&env);
    let c3 = Address::generate(&env);
    shard1.add_counterparty_link(&wallet_a, &c1, &pair);
    shard1.add_counterparty_link(&wallet_a, &c2, &pair);
    shard1.add_counterparty_link(&wallet_a, &c3, &pair);

    // Shard 2: wallet_a has 5 counterparties (more than shard 1, so max = 5).
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

    // Verify per-shard depths are independent
    assert_eq!(shard1.get_contagion_depth(&wallet_a, &pair), 3);
    assert_eq!(shard2.get_contagion_depth(&wallet_a, &pair), 5);

    // The aggregator should return the max across shards — no panic, no hang.
    let depth = agg_client.contagion_depth_across_shards(&wallet_a, &pair);
    assert_eq!(depth, 5, "should return max contagion depth across shards");

    // Also verify a wallet with no counterparties still works fine
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
