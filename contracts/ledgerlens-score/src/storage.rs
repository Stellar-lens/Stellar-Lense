use soroban_sdk::{Env, Vec, Address};
use crate::types::GateDataKey;

pub fn get_gate_open(env: &Env) -> bool {
    env.storage().instance().get(&GateDataKey::GateOpen).unwrap_or(true)
}

pub fn set_gate_open(env: &Env, open: bool) {
    env.storage().instance().set(&GateDataKey::GateOpen, &open);
}

pub fn get_gate_callers(env: &Env) -> Vec<Address> {
    env.storage().instance().get(&GateDataKey::GateCallers).unwrap_or_else(|| Vec::new(env))
}

pub fn set_gate_callers(env: &Env, callers: &Vec<Address>) {
    env.storage().instance().set(&GateDataKey::GateCallers, callers);
}
