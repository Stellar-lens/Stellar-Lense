//! Smoke test verifying that contract upgrade preserves score and configuration integrity.
//!
//! This test exercises the full upgrade lifecycle: proposing a no-op upgrade (uploading
//! the same WASM), advancing time past the delay, executing the upgrade, and verifying
//! that all stored scores and admin-configurable parameters remain unchanged.

use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, Ledger as _},
    Address, Bytes, Env, Vec,
};

use crate::{
    constants::{DEFAULT_UPGRADE_DELAY_SECS, MIN_COOLDOWN_SECS},
    parameter_governance::param_key_cooldown,
    LedgerLensScoreContract, LedgerLensScoreContractClient,
};

const START_TS: u64 = 1_700_000_000;

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();
    env.budget().reset_unlimited();
    env.ledger().with_mut(|l| l.timestamp = START_TS);

    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);

    let admin = Address::generate(&env);
    let service = Address::generate(&env);

    (env, client, admin, service)
}

/// Upload the same WASM bytecode to create a no-op upgrade target.
fn upload_current_wasm(env: &Env) -> soroban_sdk::BytesN<32> {
    env.deployer().upload_contract_wasm(Bytes::new(env))
}

/// Advance the ledger timestamp to a specific value.
fn advance_to(env: &Env, ts: u64) {
    env.ledger().with_mut(|l| l.timestamp = ts);
}

#[test]
fn test_upgrade_preserves_score_integrity() {
    let (env, client, admin, service) = setup();
    client.initialize(&admin, &service);

    // ── Submit initial scores across multiple wallets and pairs ─────────────────

    let wallet1 = Address::generate(&env);
    let wallet2 = Address::generate(&env);
    let wallet3 = Address::generate(&env);
    let pair1 = symbol_short!("XLM_USDC");
    let pair2 = symbol_short!("BTC_USDT");

    // Record submitted scores for later verification. Repeated (wallet, pair)
    // entries are spaced beyond the default cooldown (3,600s) so each update
    // is actually accepted rather than rate-limited.
    let scores = [
        (wallet1.clone(), pair1.clone(), 42, 80, 1, START_TS),
        (wallet2.clone(), pair1.clone(), 27, 90, 1, START_TS + 100),
        (wallet3.clone(), pair1.clone(), 10, 70, 1, START_TS + 200),
        (wallet1.clone(), pair2.clone(), 55, 75, 1, START_TS + 300),
        (wallet2.clone(), pair2.clone(), 88, 60, 1, START_TS + 400),
        (wallet3.clone(), pair2.clone(), 95, 65, 1, START_TS + 500),
        (wallet1.clone(), pair1.clone(), 43, 85, 1, START_TS + 3_700),
        (wallet2.clone(), pair1.clone(), 28, 92, 1, START_TS + 3_800),
        (wallet3.clone(), pair1.clone(), 11, 75, 1, START_TS + 3_900),
        (wallet3.clone(), pair2.clone(), 96, 68, 1, START_TS + 4_200),
    ];

    for (wallet, pair, score, confidence, model_ver, ts) in &scores {
        advance_to(&env, *ts);
        client.submit_score(
            &Vec::new(&env),
            wallet,
            pair,
            score,
            &false,
            &false,
            ts,
            confidence,
            model_ver,
            &None,
        );
    }

    // ── Capture configuration state before upgrade ────────────────────────────

    let cooldown_before = client.get_cooldown();
    let history_depth_before = client.get_history_max_depth();
    let decay_before = client.get_decay_rate();
    let threshold_before = client.get_risk_threshold();

    // ── Propose no-op upgrade ──────────────────────────────────────────────────

    let wasm_hash = upload_current_wasm(&env);
    client.propose_upgrade(&Vec::new(&env), &wasm_hash);

    // Verify proposal was stored
    let proposal = client.get_pending_upgrade();
    assert_eq!(proposal.new_wasm_hash, wasm_hash);
    let last_submission_ts = START_TS + 4_200;
    assert_eq!(proposal.executable_after, last_submission_ts + DEFAULT_UPGRADE_DELAY_SECS);

    // ── Advance time past the upgrade delay ────────────────────────────────────

    advance_to(&env, last_submission_ts + DEFAULT_UPGRADE_DELAY_SECS);

    // Execute the upgrade
    client.execute_upgrade(&Vec::new(&env));

    // ── Verify all scores are intact ───────────────────────────────────────────
    // Only the most recent entry per (wallet, pair) reflects live storage —
    // earlier duplicate entries in `scores` were overwritten by later updates.

    for (idx, (wallet, pair, expected_score, expected_conf, expected_model, _ts)) in
        scores.iter().enumerate()
    {
        let superseded = scores[idx + 1..].iter().any(|(w, p, ..)| w == wallet && p == pair);
        if superseded {
            continue;
        }
        let retrieved = client.get_score(wallet, pair);

        assert_eq!(
            retrieved.score, *expected_score,
            "Score mismatch for {:?} / {:?}",
            wallet, pair
        );
        assert_eq!(
            retrieved.confidence, *expected_conf,
            "Confidence mismatch for {:?} / {:?}",
            wallet, pair
        );
        assert_eq!(
            retrieved.model_version, *expected_model,
            "Model version mismatch for {:?} / {:?}",
            wallet, pair
        );
    }

    // ── Verify configuration parameters are unchanged ────────────────────────

    assert_eq!(
        client.get_cooldown(),
        cooldown_before,
        "Cooldown should be unchanged after upgrade"
    );
    assert_eq!(
        client.get_history_max_depth(),
        history_depth_before,
        "History depth should be unchanged after upgrade"
    );
    assert_eq!(
        client.get_decay_rate(),
        decay_before,
        "Decay rate should be unchanged after upgrade"
    );
    assert_eq!(
        client.get_risk_threshold(),
        threshold_before,
        "Risk threshold should be unchanged after upgrade"
    );

    // Verify the admin and service are still the same
    assert_eq!(client.get_admin(), admin, "Admin should be unchanged after upgrade");
    assert_eq!(client.get_service(), service, "Service should be unchanged after upgrade");
}

/// Extends the smoke test to cover state not exercised above: the admin
/// signer set, global and per-pair pause flags, a still-pending parameter
/// proposal, and rent (TTL) metadata for a score entry.
#[test]
fn test_upgrade_preserves_signers_pauses_and_pending_state() {
    let (env, client, admin, service) = setup();
    client.initialize(&admin, &service);

    let extra_signer = Address::generate(&env);
    client.add_admin_signer(&Vec::new(&env), &extra_signer);

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLM_USDC");
    let paused_pair = symbol_short!("BTC_USDT");
    client.submit_score(
        &Vec::new(&env),
        &wallet,
        &pair,
        &42,
        &false,
        &false,
        &START_TS,
        &80,
        &1,
        &None,
    );

    client.pause(&Vec::new(&env));
    client.set_pair_paused(&paused_pair, &true);

    let proposal_value = Bytes::from_array(&env, &MIN_COOLDOWN_SECS.to_be_bytes());
    let proposal_id =
        client.propose_parameter_change(&Vec::new(&env), &param_key_cooldown(), &proposal_value);

    // ── Capture state before upgrade ───────────────────────────────────────────

    let signers_before = client.get_admin_signers();
    let paused_before = client.is_paused();
    let pair_paused_before = client.is_pair_paused(&paused_pair);
    let proposal_before = client.get_parameter_proposal(&proposal_id);
    let ttl_before = client.get_entry_ttl(&wallet, &pair);

    // ── Upgrade ─────────────────────────────────────────────────────────────────

    let wasm_hash = upload_current_wasm(&env);
    client.propose_upgrade(&Vec::new(&env), &wasm_hash);
    advance_to(&env, START_TS + DEFAULT_UPGRADE_DELAY_SECS);
    client.execute_upgrade(&Vec::new(&env));

    // ── Verify preserved state ───────────────────────────────────────────────────

    assert_eq!(
        client.get_admin_signers(),
        signers_before,
        "Admin signer set should be unchanged after upgrade"
    );
    assert_eq!(
        client.is_paused(),
        paused_before,
        "Global pause flag should be unchanged after upgrade"
    );
    assert_eq!(
        client.is_pair_paused(&paused_pair),
        pair_paused_before,
        "Per-pair pause flag should be unchanged after upgrade"
    );
    assert_eq!(
        client.get_parameter_proposal(&proposal_id),
        proposal_before,
        "Pending parameter proposal should be unchanged after upgrade"
    );
    assert_eq!(
        client.get_entry_ttl(&wallet, &pair),
        ttl_before,
        "Score entry TTL/rent metadata should be unchanged after upgrade"
    );
}
