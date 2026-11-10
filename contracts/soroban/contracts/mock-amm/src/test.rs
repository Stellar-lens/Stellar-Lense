use super::*;
use soroban_sdk::testutils::{Address as _, Ledger};
use soroban_sdk::vec;
use stellar_lense_registry::{Method, RiskRegistry, RiskRegistryClient};

const PAIR: &str = "XLM/USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN";
const NOW: u64 = 1_800_000_000;

struct World<'a> {
    env: Env,
    amm: MockAmmClient<'a>,
    registry: RiskRegistryClient<'a>,
    admin: Address,
    signer: Address,
    pair: String,
}

fn world<'a>() -> World<'a> {
    let env = Env::default();
    env.mock_all_auths();
    env.ledger().with_mut(|l| l.timestamp = NOW);
    let admin = Address::generate(&env);
    let signer = Address::generate(&env);
    let registry_id = env.register_contract(None, RiskRegistry);
    let registry = RiskRegistryClient::new(&env, &registry_id);
    registry.initialize(&admin, &vec![&env, signer.clone()], &70);
    let amm = MockAmmClient::new(&env, &env.register_contract(None, MockAmm));
    amm.initialize(&admin, &registry_id, &70, &86_400);
    let pair = String::from_str(&env, PAIR);
    World { env, amm, registry, admin, signer, pair }
}

fn scored(w: &World, score: u32, age: u64) -> Address {
    let trader = Address::generate(&w.env);
    w.registry.submit_score(
        &w.signer,
        &trader,
        &w.pair,
        &score,
        &80,
        &Method::Heuristic,
        &(NOW - age),
    );
    trader
}

#[test]
fn low_risk_wallet_can_swap() {
    let w = world();
    let trader = scored(&w, 20, 60);
    assert_eq!(w.amm.preview(&trader, &w.pair), Decision::Allow);
    assert_eq!(w.amm.swap(&trader, &w.pair, &1_000), 1_000);
}

#[test]
fn high_risk_wallet_is_refused() {
    let w = world();
    let trader = scored(&w, 85, 60);
    assert_eq!(w.amm.preview(&trader, &w.pair), Decision::HighRisk);
    assert_eq!(w.amm.try_swap(&trader, &w.pair, &1_000), Err(Ok(Error::HighRiskWallet)));
}

#[test]
fn unknown_and_stale_fail_closed_by_default_then_open_when_configured() {
    let w = world();
    let unknown = Address::generate(&w.env);
    let stale = scored(&w, 10, 3 * 86_400);
    assert_eq!(w.amm.try_swap(&unknown, &w.pair, &5), Err(Ok(Error::NoScore)));
    assert_eq!(w.amm.try_swap(&stale, &w.pair, &5), Err(Ok(Error::StaleScore)));

    w.amm.set_fail_open(&w.admin, &true);
    assert_eq!(w.amm.swap(&unknown, &w.pair, &5), 5);
    assert_eq!(w.amm.swap(&stale, &w.pair, &5), 5);
    // Fail-open never lets a high-risk wallet through.
    let risky = scored(&w, 99, 60);
    assert_eq!(w.amm.try_swap(&risky, &w.pair, &5), Err(Ok(Error::HighRiskWallet)));
}

#[test]
fn registry_update_changes_the_decision() {
    let w = world();
    let trader = scored(&w, 20, 120);
    assert_eq!(w.amm.swap(&trader, &w.pair, &1), 1);
    w.registry.submit_score(&w.signer, &trader, &w.pair, &90, &80, &Method::Heuristic, &(NOW - 60));
    assert_eq!(w.amm.try_swap(&trader, &w.pair, &1), Err(Ok(Error::HighRiskWallet)));
}

#[test]
fn swap_requires_trader_auth_and_positive_amount() {
    let w = world();
    let trader = scored(&w, 20, 60);
    assert_eq!(w.amm.try_swap(&trader, &w.pair, &0), Err(Ok(Error::InvalidAmount)));
    w.amm.swap(&trader, &w.pair, &1);
    assert_eq!(w.env.auths()[0].0, trader);
}

#[test]
fn only_admin_changes_policy() {
    let w = world();
    let mallory = Address::generate(&w.env);
    assert_eq!(w.amm.try_set_fail_open(&mallory, &true), Err(Ok(Error::NotAdmin)));
    assert!(!w.amm.config().fail_open);
}
