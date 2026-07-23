//! Composability test for the ledgerlens-aggregator fallback pattern
//! (issue #434): distinguishing "the aggregator is unavailable" (no shards
//! registered, or a shard's cross-contract call itself failed) from "the
//! aggregator's shards genuinely agree this wallet is too risky" — both of
//! which collapse to the same `query_risk_gate() == false` if an integrator
//! only looks at that one boolean.
//!
//! See `examples/aggregator_gate_example.rs` (`AggregatorGatedAmm::swap`) for
//! the full reference pattern this test exercises directly against a real
//! deployed `LedgerLensAggregator` and `LedgerLensScoreContract` shard.

use ledgerlens_aggregator::{LedgerLensAggregator, LedgerLensAggregatorClient};
use ledgerlens_score::{LedgerLensScoreContract, LedgerLensScoreContractClient};
use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, Ledger as _},
    Address, Env, Symbol, Vec,
};

const GATE_THRESHOLD: u32 = 75;

/// The gate outcome an integrator should act on: a genuine risk-based
/// rejection vs. the aggregator being unable to meaningfully answer at all.
#[derive(Debug, PartialEq)]
enum GateOutcome {
    Passed,
    RejectedHighRisk,
    Unavailable,
}

/// The recommended fallback-policy pattern (issue #434): distinguishes a
/// genuine risk-based rejection from aggregator unavailability using only
/// the aggregator's public API (`get_shards`, `get_last_shard_failure`,
/// `query_risk_gate`). Fails closed (`Unavailable`) whenever the aggregator
/// cannot meaningfully answer, matching the recommendation documented in
/// `docs/aggregator-error-mapping.md`.
fn gated_query(
    aggregator: &LedgerLensAggregatorClient,
    wallet: &Address,
    pair: &Symbol,
) -> GateOutcome {
    if aggregator.get_shards().is_empty() {
        return GateOutcome::Unavailable;
    }

    let failure_before = aggregator.get_last_shard_failure();
    let passes = aggregator.query_risk_gate(wallet, pair, &GATE_THRESHOLD);

    if passes {
        return GateOutcome::Passed;
    }

    // A `false` result is ambiguous on its own: it's what both a genuine
    // rejection *and* a shard failure look like. Comparing the failure
    // marker before/after this exact call resolves the ambiguity.
    let failure_after = aggregator.get_last_shard_failure();
    if failure_after != failure_before {
        GateOutcome::Unavailable
    } else {
        GateOutcome::RejectedHighRisk
    }
}

struct Fixture<'a> {
    env: Env,
    aggregator: LedgerLensAggregatorClient<'a>,
    shard: LedgerLensScoreContractClient<'a>,
    wallet: Address,
    pair: Symbol,
}

/// Deploys an aggregator and a real `LedgerLensScoreContract` shard, but does
/// **not** register the shard with the aggregator — callers opt in via
/// `f.aggregator.add_shard(&f.shard.address)` so each test controls exactly
/// which "unavailable" scenario it exercises.
fn setup<'a>() -> Fixture<'a> {
    let env = Env::default();
    env.mock_all_auths();
    env.ledger().with_mut(|l| l.timestamp = 100_000);

    let agg_id = env.register_contract(None, LedgerLensAggregator);
    let aggregator = LedgerLensAggregatorClient::new(&env, &agg_id);
    aggregator.initialize(&Address::generate(&env));

    let shard_id = env.register_contract(None, LedgerLensScoreContract);
    let shard = LedgerLensScoreContractClient::new(&env, &shard_id);
    shard.initialize(&Address::generate(&env), &Address::generate(&env));

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");

    Fixture { env, aggregator, shard, wallet, pair }
}

fn submit_score(f: &Fixture, score: u32) {
    f.shard.submit_score(
        &Vec::new(&f.env),
        &f.wallet,
        &f.pair,
        &score,
        &false,
        &false,
        &f.env.ledger().timestamp(),
        &90,
        &1,
        &None,
    );
}

#[test]
fn no_shards_registered_is_unavailable_not_rejection() {
    let f = setup(); // shard deployed but never added to the aggregator
    assert_eq!(gated_query(&f.aggregator, &f.wallet, &f.pair), GateOutcome::Unavailable);
}

#[test]
fn healthy_low_risk_wallet_passes() {
    let f = setup();
    f.aggregator.add_shard(&f.shard.address);
    submit_score(&f, 10); // well under GATE_THRESHOLD

    assert_eq!(gated_query(&f.aggregator, &f.wallet, &f.pair), GateOutcome::Passed);
}

#[test]
fn healthy_high_risk_wallet_is_genuine_rejection() {
    let f = setup();
    f.aggregator.add_shard(&f.shard.address);
    submit_score(&f, 90); // at/above GATE_THRESHOLD

    assert_eq!(gated_query(&f.aggregator, &f.wallet, &f.pair), GateOutcome::RejectedHighRisk);
}

/// Core fallback scenario: the wallet would genuinely pass if the shard were
/// healthy, but the shard is globally paused, so its cross-contract call
/// fails and the aggregator's AND-across-shards logic returns `false` — the
/// same boolean a genuine rejection would produce. The fallback pattern must
/// still classify this as `Unavailable`, not `RejectedHighRisk`.
#[test]
fn paused_shard_is_unavailable_not_rejection() {
    let f = setup();
    f.aggregator.add_shard(&f.shard.address);
    submit_score(&f, 10); // would pass on a healthy shard

    f.shard.pause(&Vec::new(&f.env));
    assert!(f.shard.is_paused());

    assert_eq!(gated_query(&f.aggregator, &f.wallet, &f.pair), GateOutcome::Unavailable);

    // Recovery: unpausing restores the genuine (passing) verdict.
    f.shard.unpause(&Vec::new(&f.env));
    assert_eq!(gated_query(&f.aggregator, &f.wallet, &f.pair), GateOutcome::Passed);
}

/// Same ambiguity, different root cause: a registered shard address that
/// was never actually deployed as a contract.
#[test]
fn unreachable_shard_is_unavailable_not_rejection() {
    let f = setup();
    let unreachable = Address::generate(&f.env); // never deployed as a contract
    f.aggregator.add_shard(&unreachable);

    assert_eq!(gated_query(&f.aggregator, &f.wallet, &f.pair), GateOutcome::Unavailable);
}
