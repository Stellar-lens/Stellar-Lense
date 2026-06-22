use soroban_sdk::{
    testutils::{Address as _, Ledger as _},
    Address, Env,
};

use crate::{
    LedgerLensScoreContract, LedgerLensScoreContractClient,
};

// ── Test helpers ──────────────────────────────────────────────────────────────

pub fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();

    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);

    let admin = Address::generate(&env);
    let service = Address::generate(&env);

    (env, client, admin, service)
}

pub fn initialized<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let (env, client, admin, service) = setup();
    env.ledger().with_mut(|l| l.timestamp = 100_000);
    client.initialize(&admin, &service);
    (env, client, admin, service)
}

// ── Initialization ────────────────────────────────────────────────────────────

#[test]
fn test_initialize() {
    let (_env, client, admin, service) = setup();
    client.initialize(&admin, &service);
    assert_eq!(client.get_admin(), admin);
    assert_eq!(client.get_service(), service);
}

