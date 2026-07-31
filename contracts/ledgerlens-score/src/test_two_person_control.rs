//! Tests for two-person control on destructive operations.

use soroban_sdk::{
    testutils::{Address as _, Ledger as _},
    Address, Env, Symbol, Vec,
};

use crate::{
    parameter_governance::param_key_cooldown, Error, LedgerLensScoreContract,
    LedgerLensScoreContractClient,
};

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();

    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);

    let admin1 = Address::generate(&env);
    let service = Address::generate(&env);
    client.initialize(&admin1, &service);

    (env, client, admin1, service)
}

fn admin_signers(env: &Env, admins: &[Address]) -> Vec<Address> {
    Vec::from_array(env, admins)
}

fn pair_symbols(env: &Env, pairs: &[&str]) -> Vec<Symbol> {
    let vec = Vec::new(env);
    let mut result = vec;
    for pair_name in pairs {
        result = result.push_back(Symbol::new(env, pair_name));
    }
    result
}

#[test]
fn test_bulk_reset_single_admin_no_policy() {
    let (env, client, admin, _service) = setup();
    let pairs = pair_symbols(&env, &["USD/EUR"]);

    client.set_pair_weight(&admin_signers(&env, &[admin.clone()]), &Symbol::new(&env, "USD/EUR"), &1000);

    let result = client.try_bulk_reset_pair_weight(&admin_signers(&env, &[admin.clone()]), &pairs);
    assert!(result.is_ok());
}

#[test]
fn test_bulk_reset_single_admin_with_policy_rejected() {
    let (env, client, admin, _service) = setup();
    let pairs = pair_symbols(&env, &["USD/EUR"]);

    client.set_pair_weight(&admin_signers(&env, &[admin.clone()]), &Symbol::new(&env, "USD/EUR"), &1000);
    client.set_require_multisig_for_destructive(&admin_signers(&env, &[admin.clone()]), &true).unwrap();

    let result = client.try_bulk_reset_pair_weight(&admin_signers(&env, &[admin.clone()]), &pairs);
    assert_eq!(result, Err(Ok(Error::InsufficientAdminSigners)));
}

#[test]
fn test_bulk_reset_multi_admin_with_policy_accepted() {
    let (env, client, admin1, _service) = setup();
    let admin2 = Address::generate(&env);
    let pairs = pair_symbols(&env, &["USD/EUR"]);

    client.set_pair_weight(&admin_signers(&env, &[admin1.clone()]), &Symbol::new(&env, "USD/EUR"), &1000);
    client.set_require_multisig_for_destructive(&admin_signers(&env, &[admin1.clone()]), &true).unwrap();

    let result = client.try_bulk_reset_pair_weight(&admin_signers(&env, &[admin1.clone(), admin2]), &pairs);
    assert!(result.is_ok());
}

#[test]
fn test_multisig_policy_toggle() {
    let (env, client, admin, _service) = setup();

    assert!(!client.get_require_multisig_for_destructive());

    client.set_require_multisig_for_destructive(&admin_signers(&env, &[admin.clone()]), &true).unwrap();
    assert!(client.get_require_multisig_for_destructive());

    client.set_require_multisig_for_destructive(&admin_signers(&env, &[admin.clone()]), &false).unwrap();
    assert!(!client.get_require_multisig_for_destructive());
}

#[test]
fn test_multisig_policy_persists_across_calls() {
    let (env, client, admin1, _service) = setup();
    let admin2 = Address::generate(&env);
    let pairs = pair_symbols(&env, &["USD/EUR", "GBP/USD"]);

    client.set_pair_weight(&admin_signers(&env, &[admin1.clone()]), &Symbol::new(&env, "USD/EUR"), &1000);
    client.set_pair_weight(&admin_signers(&env, &[admin1.clone()]), &Symbol::new(&env, "GBP/USD"), &2000);
    client.set_require_multisig_for_destructive(&admin_signers(&env, &[admin1.clone()]), &true).unwrap();

    let result1 = client.try_bulk_reset_pair_weight(&admin_signers(&env, &[admin1.clone(), admin2.clone()]), &pairs);
    assert!(result1.is_ok());

    client.set_pair_weight(&admin_signers(&env, &[admin1.clone()]), &Symbol::new(&env, "USD/EUR"), &3000);
    let pairs2 = pair_symbols(&env, &["USD/EUR"]);
    let result2 = client.try_bulk_reset_pair_weight(&admin_signers(&env, &[admin1.clone(), admin2.clone()]), &pairs2);
    assert!(result2.is_ok());
}

#[test]
fn test_policy_default_disabled() {
    let (env, client, admin, _service) = setup();
    let pairs = pair_symbols(&env, &["USD/EUR"]);

    client.set_pair_weight(&admin_signers(&env, &[admin.clone()]), &Symbol::new(&env, "USD/EUR"), &1000);

    assert!(!client.get_require_multisig_for_destructive());

    let result = client.try_bulk_reset_pair_weight(&admin_signers(&env, &[admin.clone()]), &pairs);
    assert!(result.is_ok());
}
