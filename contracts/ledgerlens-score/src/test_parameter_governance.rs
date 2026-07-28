//! Tests for the time-locked parameter change governance mechanism.

use soroban_sdk::{
    testutils::{Address as _, Ledger as _},
    Address, Bytes, Env, Vec,
};

use crate::{
    constants::{
        DEFAULT_COOLDOWN_SECS, DEFAULT_UPGRADE_DELAY_SECS, MAX_PENDING_PARAMETER_PROPOSALS,
        MIN_COOLDOWN_SECS,
    },
    parameter_governance::param_key_cooldown,
    storage,
    types::ParameterProposalStatus,
    Error, LedgerLensScoreContract, LedgerLensScoreContractClient,
};

const START_TS: u64 = 1_700_000_000;

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();
    env.ledger().with_mut(|l| l.timestamp = START_TS);

    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);

    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    client.initialize(&admin, &service);

    (env, client, admin, service)
}

fn admin_signers(env: &Env, admin: &Address) -> Vec<Address> {
    Vec::from_array(env, [admin.clone()])
}

fn service_signers(env: &Env, service: &Address) -> Vec<Address> {
    Vec::from_array(env, [service.clone()])
}

fn encode_u64(env: &Env, value: u64) -> Bytes {
    Bytes::from_array(env, &value.to_be_bytes())
}

fn advance_to(env: &Env, ts: u64) {
    env.ledger().with_mut(|l| l.timestamp = ts);
}

#[test]
fn test_proposal_created_time_passes_executed() {
    let (env, client, admin, _service) = setup();
    let new_cooldown = MIN_COOLDOWN_SECS;
    let value = encode_u64(&env, new_cooldown);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    assert_eq!(proposal_id, 1);
    let record = client.get_parameter_proposal(&proposal_id);
    assert_eq!(record.status, ParameterProposalStatus::Pending);
    assert_eq!(record.proposal.proposed_at, START_TS);
    assert_eq!(record.proposal.time_lock_secs, DEFAULT_UPGRADE_DELAY_SECS);

    advance_to(&env, START_TS + DEFAULT_UPGRADE_DELAY_SECS);
    client.execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);

    assert_eq!(client.get_cooldown(), new_cooldown);
    let executed = client.get_parameter_proposal(&proposal_id);
    assert_eq!(executed.status, ParameterProposalStatus::Executed);
}

#[test]
fn test_vetoed_proposal_cannot_be_executed() {
    let (env, client, admin, service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    client.veto_parameter_change(&service_signers(&env, &service), &proposal_id);

    advance_to(&env, START_TS + DEFAULT_UPGRADE_DELAY_SECS);
    let result = client.try_execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);
    assert_eq!(result, Err(Ok(Error::ParameterProposalVetoed)));
    assert_eq!(client.get_cooldown(), DEFAULT_COOLDOWN_SECS);
}

#[test]
fn test_execute_before_timelock_rejected() {
    let (env, client, admin, _service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    let result = client.try_execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);
    assert_eq!(result, Err(Ok(Error::ParameterProposalNotReady)));

    advance_to(&env, START_TS + DEFAULT_UPGRADE_DELAY_SECS - 1);
    let result = client.try_execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);
    assert_eq!(result, Err(Ok(Error::ParameterProposalNotReady)));
}

#[test]
fn test_maximum_pending_proposals_cap() {
    let (env, client, admin, _service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    env.as_contract(&client.address, || {
        storage::test_seed_pending_parameter_proposals(
            &env,
            MAX_PENDING_PARAMETER_PROPOSALS,
            &admin,
            &param_key_cooldown(),
            &value,
        );
    });

    let result = client.try_propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );
    assert_eq!(result, Err(Ok(Error::TooManyPendingParameterProposals)));
}

#[test]
fn test_veto_after_half_timelock_rejected() {
    let (env, client, admin, service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    let veto_deadline = START_TS + DEFAULT_UPGRADE_DELAY_SECS / 2;
    advance_to(&env, veto_deadline + 1);

    let result = client.try_veto_parameter_change(&service_signers(&env, &service), &proposal_id);
    assert_eq!(result, Err(Ok(Error::ParameterProposalVetoPeriodEnded)));
}

#[test]
fn test_expired_proposal_cannot_execute() {
    let (env, client, admin, _service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    let expiry = START_TS + DEFAULT_UPGRADE_DELAY_SECS * 2 + 1;
    advance_to(&env, expiry);

    let result = client.try_execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);
    assert_eq!(result, Err(Ok(Error::ParameterProposalExpired)));

    env.as_contract(&client.address, || {
        storage::mark_parameter_proposal_status(
            &env,
            proposal_id,
            ParameterProposalStatus::Expired,
        );
    });

    let record = client.get_parameter_proposal(&proposal_id);
    assert_eq!(record.status, ParameterProposalStatus::Expired);
}

#[test]
fn test_executed_proposal_cannot_be_reexecuted() {
    let (env, client, admin, _service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    advance_to(&env, START_TS + DEFAULT_UPGRADE_DELAY_SECS);
    client.execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);

    let result = client.try_execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);
    assert_eq!(result, Err(Ok(Error::ParameterProposalAlreadyExecuted)));
}

#[test]
fn test_veto_before_half_timelock_succeeds() {
    let (env, client, admin, service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    client.veto_parameter_change(&service_signers(&env, &service), &proposal_id);

    let record = client.get_parameter_proposal(&proposal_id);
    assert_eq!(record.status, ParameterProposalStatus::Vetoed);
    assert!(client.get_pending_param_prop_ids().is_empty());
}

#[test]
fn test_cleanup_expired_proposals_removes_old_expired() {
    let (env, client, admin, _service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    let expiry = START_TS + DEFAULT_UPGRADE_DELAY_SECS * 2 + 1;
    advance_to(&env, expiry);
    let _ = client.try_execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);

    let record = client.get_parameter_proposal(&proposal_id);
    assert_eq!(record.status, ParameterProposalStatus::Expired);

    advance_to(&env, expiry + 48 * 3600 + 1);
    let count = client.cleanup_expired_parameter_proposals(&admin_signers(&env, &admin));
    assert_eq!(count, 1);
}

#[test]
fn test_cleanup_respects_ttl_buffer() {
    let (env, client, admin, _service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    let expiry = START_TS + DEFAULT_UPGRADE_DELAY_SECS * 2 + 1;
    advance_to(&env, expiry);
    let _ = client.try_execute_parameter_change(&admin_signers(&env, &admin), &proposal_id);

    advance_to(&env, expiry + 24 * 3600);
    let count = client.cleanup_expired_parameter_proposals(&admin_signers(&env, &admin));
    assert_eq!(count, 0);

    advance_to(&env, expiry + 48 * 3600 + 1);
    let count = client.cleanup_expired_parameter_proposals(&admin_signers(&env, &admin));
    assert_eq!(count, 1);
}

#[test]
fn test_cleanup_preserves_non_expired() {
    let (env, client, admin, _service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let _proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    advance_to(&env, START_TS + DEFAULT_UPGRADE_DELAY_SECS);

    let count = client.cleanup_expired_parameter_proposals(&admin_signers(&env, &admin));
    assert_eq!(count, 0);

    let pending = client.get_pending_param_prop_ids();
    assert_eq!(pending.len(), 1);
}

#[test]
fn test_cleanup_idempotent() {
    let (env, client, admin, _service) = setup();
    let value = encode_u64(&env, MIN_COOLDOWN_SECS);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    let expiry = START_TS + DEFAULT_UPGRADE_DELAY_SECS * 2 + 1;
    advance_to(&env, expiry + 48 * 3600 + 1);

    let count1 = client.cleanup_expired_parameter_proposals(&admin_signers(&env, &admin));
    assert_eq!(count1, 1);

    let count2 = client.cleanup_expired_parameter_proposals(&admin_signers(&env, &admin));
    assert_eq!(count2, 0);
}

#[test]
fn test_simulate_parameter_change_cooldown() {
    let (env, client, _admin, _service) = setup();
    let new_cooldown = MIN_COOLDOWN_SECS + 100;
    let value = encode_u64(&env, new_cooldown);

    let sim = client.simulate_parameter_change(&param_key_cooldown(), &value);
    assert_eq!(sim.param_key, param_key_cooldown());
    assert_eq!(sim.new_value, value);
    assert!(sim.affected_capabilities.len() >= 1);
}

#[test]
fn test_simulate_parameter_change_deterministic() {
    let (env, client, _admin, _service) = setup();
    let new_cooldown = MIN_COOLDOWN_SECS + 200;
    let value = encode_u64(&env, new_cooldown);

    let sim1 = client.simulate_parameter_change(&param_key_cooldown(), &value);
    let sim2 = client.simulate_parameter_change(&param_key_cooldown(), &value);

    assert_eq!(sim1.param_key, sim2.param_key);
    assert_eq!(sim1.current_value, sim2.current_value);
    assert_eq!(sim1.new_value, sim2.new_value);
    assert_eq!(sim1.execution_window_start, sim2.execution_window_start);
    assert_eq!(sim1.execution_window_end, sim2.execution_window_end);
}

#[test]
fn test_get_proposal_simulation() {
    let (env, client, admin, _service) = setup();
    let new_cooldown = MIN_COOLDOWN_SECS + 300;
    let value = encode_u64(&env, new_cooldown);

    let proposal_id = client.propose_parameter_change(
        &admin_signers(&env, &admin),
        &param_key_cooldown(),
        &value,
    );

    let output = client.get_proposal_simulation(&proposal_id);
    assert_eq!(output.proposal_id, proposal_id);
    assert_eq!(output.simulation.param_key, param_key_cooldown());
    assert_eq!(output.simulation.new_value, value);
    assert_eq!(output.simulation.execution_window_start, START_TS + DEFAULT_UPGRADE_DELAY_SECS);
    assert_eq!(output.simulation.execution_window_end, START_TS + DEFAULT_UPGRADE_DELAY_SECS * 2);
}

#[test]
fn test_simulate_nonexistent_proposal() {
    let (env, client, _admin, _service) = setup();
    let result = client.try_get_proposal_simulation(&999);
    assert_eq!(result, Err(Ok(Error::ParameterProposalNotFound)));
}
