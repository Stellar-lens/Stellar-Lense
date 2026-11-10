extern crate std;

use super::*;
use soroban_sdk::testutils::{Address as _, Events, Ledger};
use soroban_sdk::{vec, IntoVal};

const PAIR: &str = "XLM/USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN";

struct Setup<'a> {
    env: Env,
    client: RiskRegistryClient<'a>,
    admin: Address,
    signer: Address,
    pair: String,
}

fn setup<'a>() -> Setup<'a> {
    let env = Env::default();
    env.mock_all_auths();
    env.ledger().with_mut(|l| l.timestamp = 1_800_000_000);
    let id = env.register_contract(None, RiskRegistry);
    let client = RiskRegistryClient::new(&env, &id);
    let admin = Address::generate(&env);
    let signer = Address::generate(&env);
    client.initialize(&admin, &vec![&env, signer.clone()], &70);
    let pair = String::from_str(&env, PAIR);
    Setup { env, client, admin, signer, pair }
}

fn submit(s: &Setup, wallet: &Address, score: u32, as_of: u64) {
    s.client.submit_score(&s.signer, wallet, &s.pair, &score, &80, &Method::Heuristic, &as_of);
}

#[test]
fn initialize_sets_state_and_only_once() {
    let s = setup();
    assert_eq!(s.client.admin(), s.admin);
    assert!(s.client.is_signer(&s.signer));
    assert_eq!(s.client.threshold(), 70);
    assert!(!s.client.is_paused());
    assert_eq!(s.client.version(), 2);
    let again = s.client.try_initialize(&s.admin, &vec![&s.env, s.signer.clone()], &70);
    assert_eq!(again, Err(Ok(Error::AlreadyInitialized)));
}

#[test]
fn initialize_rejects_bad_config() {
    let env = Env::default();
    env.mock_all_auths();
    let client = RiskRegistryClient::new(&env, &env.register_contract(None, RiskRegistry));
    let admin = Address::generate(&env);
    assert_eq!(client.try_initialize(&admin, &Vec::new(&env), &70), Err(Ok(Error::NoSigners)));
    assert_eq!(
        client.try_initialize(&admin, &vec![&env, Address::generate(&env)], &101),
        Err(Ok(Error::InvalidThreshold))
    );
}

#[test]
fn signer_submits_and_anyone_reads() {
    let s = setup();
    let wallet = Address::generate(&s.env);
    submit(&s, &wallet, 85, 1_799_999_000);
    let stored = s.client.get_score(&wallet, &s.pair).unwrap();
    assert_eq!(stored.score, 85);
    assert_eq!(stored.confidence, 80);
    assert_eq!(stored.method, Method::Heuristic);
    assert_eq!(stored.as_of, 1_799_999_000);
    assert!(s.client.is_flagged(&wallet, &s.pair));
    assert_eq!(s.client.get_score(&Address::generate(&s.env), &s.pair), None);
}

#[test]
fn submit_requires_signer_auth() {
    let s = setup();
    let wallet = Address::generate(&s.env);
    submit(&s, &wallet, 10, 1);
    let auths = s.env.auths();
    assert_eq!(auths.len(), 1);
    assert_eq!(auths[0].0, s.signer);
}

#[test]
fn non_signer_cannot_submit() {
    let s = setup();
    let stranger = Address::generate(&s.env);
    let wallet = Address::generate(&s.env);
    let result =
        s.client.try_submit_score(&stranger, &wallet, &s.pair, &50, &50, &Method::Heuristic, &1);
    assert_eq!(result, Err(Ok(Error::NotSigner)));
}

#[test]
#[should_panic]
fn submit_without_any_auth_panics() {
    let env = Env::default();
    let id = env.register_contract(None, RiskRegistry);
    let client = RiskRegistryClient::new(&env, &id);
    let admin = Address::generate(&env);
    let signer = Address::generate(&env);
    env.mock_all_auths();
    client.initialize(&admin, &vec![&env, signer.clone()], &70);
    env.set_auths(&[]);
    client.submit_score(
        &signer,
        &Address::generate(&env),
        &String::from_str(&env, PAIR),
        &50,
        &50,
        &Method::Heuristic,
        &1,
    );
}

#[test]
fn rejects_out_of_range_values_and_bad_pairs() {
    let s = setup();
    let w = Address::generate(&s.env);
    let m = Method::Ml;
    assert_eq!(
        s.client.try_submit_score(&s.signer, &w, &s.pair, &101, &50, &m, &1),
        Err(Ok(Error::InvalidScore))
    );
    assert_eq!(
        s.client.try_submit_score(&s.signer, &w, &s.pair, &50, &101, &m, &1),
        Err(Ok(Error::InvalidConfidence))
    );
    let empty = String::from_str(&s.env, "");
    assert_eq!(
        s.client.try_submit_score(&s.signer, &w, &empty, &50, &50, &m, &1),
        Err(Ok(Error::InvalidPair))
    );
}

#[test]
fn older_submission_cannot_overwrite_newer() {
    let s = setup();
    let wallet = Address::generate(&s.env);
    submit(&s, &wallet, 40, 2_000);
    let older = s.client.try_submit_score(
        &s.signer,
        &wallet,
        &s.pair,
        &90,
        &80,
        &Method::Heuristic,
        &1_000,
    );
    assert_eq!(older, Err(Ok(Error::StaleSubmission)));
    submit(&s, &wallet, 45, 2_000); // same as_of: allowed (re-publish)
    assert_eq!(s.client.get_score(&wallet, &s.pair).unwrap().score, 45);
}

#[test]
fn batch_submit_is_all_or_nothing_and_bounded() {
    let s = setup();
    let a = Address::generate(&s.env);
    let b = Address::generate(&s.env);
    let row = |w: &Address, score: u32| ScoreInput {
        wallet: w.clone(),
        pair: s.pair.clone(),
        score,
        confidence: 60,
        method: Method::Heuristic,
        as_of: 10,
    };
    s.client.submit_scores(&s.signer, &vec![&s.env, row(&a, 20), row(&b, 75)]);
    assert_eq!(s.client.get_score(&b, &s.pair).unwrap().score, 75);

    let c = Address::generate(&s.env);
    let bad = s.client.try_submit_scores(&s.signer, &vec![&s.env, row(&c, 30), row(&a, 200)]);
    assert_eq!(bad, Err(Ok(Error::InvalidScore)));
    assert_eq!(s.client.get_score(&c, &s.pair), None); // rolled back

    let mut big = Vec::new(&s.env);
    for _ in 0..=MAX_BATCH {
        big.push_back(row(&Address::generate(&s.env), 1));
    }
    assert_eq!(s.client.try_submit_scores(&s.signer, &big), Err(Ok(Error::BatchTooLarge)));
}

#[test]
fn pair_score_round_trip_and_validation() {
    let s = setup();
    s.client.submit_pair_score(&s.signer, &s.pair, &32, &58, &2, &40, &100);
    let p = s.client.get_pair_score(&s.pair).unwrap();
    assert_eq!((p.average, p.max, p.flagged, p.total, p.as_of), (32, 58, 2, 40, 100));
    assert_eq!(
        s.client.try_submit_pair_score(&s.signer, &s.pair, &60, &50, &0, &1, &200),
        Err(Ok(Error::InvalidPairScore))
    );
    assert_eq!(
        s.client.try_submit_pair_score(&s.signer, &s.pair, &10, &20, &5, &1, &200),
        Err(Ok(Error::InvalidPairScore))
    );
    assert_eq!(
        s.client.try_submit_pair_score(&s.signer, &s.pair, &10, &20, &0, &1, &50),
        Err(Ok(Error::StaleSubmission))
    );
}

#[test]
fn check_returns_each_decision() {
    let s = setup();
    let now = s.env.ledger().timestamp();
    let risky = Address::generate(&s.env);
    let clean = Address::generate(&s.env);
    let old = Address::generate(&s.env);
    submit(&s, &risky, 90, now - 60);
    submit(&s, &clean, 10, now - 60);
    submit(&s, &old, 10, now - 10_000);
    let day = 86_400;
    assert_eq!(s.client.check(&risky, &s.pair, &70, &day), Decision::HighRisk);
    assert_eq!(s.client.check(&clean, &s.pair, &70, &day), Decision::Allow);
    assert_eq!(s.client.check(&old, &s.pair, &70, &3_600), Decision::Stale);
    assert_eq!(s.client.check(&old, &s.pair, &70, &day), Decision::Allow);
    let nobody = Address::generate(&s.env);
    assert_eq!(s.client.check(&nobody, &s.pair, &70, &day), Decision::NoScore);
    // max_score is the caller's own bar, independent of the registry threshold.
    assert_eq!(s.client.check(&clean, &s.pair, &10, &day), Decision::HighRisk);
}

#[test]
fn pause_blocks_writes_not_reads() {
    let s = setup();
    let wallet = Address::generate(&s.env);
    submit(&s, &wallet, 50, 1);
    s.client.pause(&s.admin);
    assert!(s.client.is_paused());
    let blocked =
        s.client.try_submit_score(&s.signer, &wallet, &s.pair, &60, &50, &Method::Heuristic, &2);
    assert_eq!(blocked, Err(Ok(Error::Paused)));
    assert_eq!(s.client.get_score(&wallet, &s.pair).unwrap().score, 50);
    s.client.unpause(&s.admin);
    submit(&s, &wallet, 60, 2);
    assert_eq!(s.client.get_score(&wallet, &s.pair).unwrap().score, 60);
}

#[test]
fn only_admin_can_administer() {
    let s = setup();
    let mallory = Address::generate(&s.env);
    assert_eq!(s.client.try_pause(&mallory), Err(Ok(Error::NotAdmin)));
    assert_eq!(s.client.try_add_signer(&mallory, &mallory), Err(Ok(Error::NotAdmin)));
    assert_eq!(s.client.try_set_threshold(&mallory, &1), Err(Ok(Error::NotAdmin)));
    assert_eq!(s.client.try_propose_admin(&mallory, &mallory), Err(Ok(Error::NotAdmin)));
    let hash = BytesN::from_array(&s.env, &[0; 32]);
    assert_eq!(s.client.try_upgrade(&mallory, &hash), Err(Ok(Error::NotAdmin)));
}

#[test]
fn signer_management_keeps_at_least_one() {
    let s = setup();
    let second = Address::generate(&s.env);
    s.client.add_signer(&s.admin, &second);
    assert!(s.client.is_signer(&second));
    s.client.remove_signer(&s.admin, &s.signer);
    assert!(!s.client.is_signer(&s.signer));
    assert_eq!(s.client.try_remove_signer(&s.admin, &second), Err(Ok(Error::NoSigners)));
    // A removed signer can no longer publish.
    let w = Address::generate(&s.env);
    assert_eq!(
        s.client.try_submit_score(&s.signer, &w, &s.pair, &1, &1, &Method::Heuristic, &1),
        Err(Ok(Error::NotSigner))
    );
}

#[test]
fn threshold_drives_is_flagged() {
    let s = setup();
    let wallet = Address::generate(&s.env);
    submit(&s, &wallet, 60, 1);
    assert!(!s.client.is_flagged(&wallet, &s.pair));
    s.client.set_threshold(&s.admin, &60);
    assert!(s.client.is_flagged(&wallet, &s.pair));
    assert_eq!(s.client.try_set_threshold(&s.admin, &101), Err(Ok(Error::InvalidThreshold)));
}

#[test]
fn two_step_admin_rotation() {
    let s = setup();
    let next = Address::generate(&s.env);
    assert_eq!(s.client.try_accept_admin(), Err(Ok(Error::NoPendingAdmin)));
    s.client.propose_admin(&s.admin, &next);
    assert_eq!(s.client.pending_admin(), Some(next.clone()));
    assert_eq!(s.client.admin(), s.admin); // not yet
    s.client.accept_admin();
    let auths = s.env.auths();
    assert_eq!(auths[0].0, next); // the nominee had to sign
    assert_eq!(s.client.admin(), next);
    assert_eq!(s.client.pending_admin(), None);
    assert_eq!(s.client.try_pause(&s.admin), Err(Ok(Error::NotAdmin)));
}

#[test]
fn score_submission_emits_event() {
    let s = setup();
    let wallet = Address::generate(&s.env);
    submit(&s, &wallet, 77, 5);
    let events = s.env.events().all();
    let last = events.last().unwrap();
    assert_eq!(last.1, (symbol_short!("score"), wallet.clone()).into_val(&s.env));
    let data: (String, u32, u64) = last.2.into_val(&s.env);
    assert_eq!(data, (s.pair.clone(), 77, 5));
}

#[test]
fn reads_work_before_initialize() {
    let env = Env::default();
    let client = RiskRegistryClient::new(&env, &env.register_contract(None, RiskRegistry));
    let pair = String::from_str(&env, PAIR);
    let wallet = Address::generate(&env);
    assert_eq!(client.get_score(&wallet, &pair), None);
    assert_eq!(client.check(&wallet, &pair, &70, &60), Decision::NoScore);
    assert_eq!(client.try_admin(), Err(Ok(Error::NotInitialized)));
}
