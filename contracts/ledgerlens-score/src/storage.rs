use soroban_sdk::{Env, Address};
use crate::types::{DataKey, TierBounds};
use crate::errors::Error;

pub fn set_signer_tier(env: &Env, signer: &Address, min_score: u32, max_score: u32) -> Result<(), Error> {
    if min_score > max_score || max_score > 100 {
        return Err(Error::InvalidSignerTier);
    }
    let bounds = TierBounds { min_score, max_score };
    env.storage().instance().set(&DataKey::SignerTier(signer.clone()), &bounds);
    Ok(())
}

pub fn get_signer_tier(env: &Env, signer: &Address) -> TierBounds {
    env.storage()
        .instance()
        .get(&DataKey::SignerTier(signer.clone()))
        .unwrap_or(TierBounds { min_score: 0, max_score: 100 })
}

pub fn remove_signer_tier(env: &Env, signer: &Address) {
    env.storage().instance().remove(&DataKey::SignerTier(signer.clone()));
}
