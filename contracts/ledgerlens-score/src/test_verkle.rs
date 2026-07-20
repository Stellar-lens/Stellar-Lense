#![cfg(test)]

//! Tests for the Verkle / KZG polynomial commitment system.
//!
//! Covers:
//! * `get_state_commitment` — initial zero state, changes after each write.
//! * `get_membership_proof` + `verify_membership` — inclusion proofs.
//! * Non-membership proofs for wallets/pairs with no score.
//! * Commitment update correctness: adding, updating, and multiple entries.
//! * Tamper-resistance: wrong score, wrong wallet, wrong pair → verify fails.
//! * Batch path (`submit_scores_batch`) updates commitment identically.

use soroban_sdk::{
    symbol_short, testutils::{Address as _, Ledger}, Address, Bytes, BytesN, Env, Vec,
};

use crate::{
    verkle::{
        self, xor32, derive_evaluation_point, derive_value_element, hash_leaf,
        encode_proof, decode_proof, commitment_to_bytes48, bytes48_to_commitment,
        verify_proof,
    },
    LedgerLensScoreContract, LedgerLensScoreContractClient, ScoreSubmission,
};

// ── Test infrastructure ──────────────────────────────────────────────────────

fn setup<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();
    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    (env, client, admin, service)
}

fn initialized<'a>() -> (Env, LedgerLensScoreContractClient<'a>, Address, Address) {
    let (env, client, admin, service) = setup();
    client.initialize(&admin, &service);
    (env, client, admin, service)
}

/// `Bytes` has no fixed-size array conversion; unpack the 97-byte proof
/// payload manually for byte-level assertions in these tests.
fn proof_to_array(proof: &Bytes) -> [u8; 97] {
    let mut arr = [0u8; 97];
    for i in 0..97u32 {
        arr[i as usize] = proof.get(i).unwrap();
    }
    arr
}

// ── Commitment structure tests ───────────────────────────────────────────────

#[test]
fn commitment_is_48_bytes_from_the_start() {
    let (_env, client, admin, service) = initialized();
    let c = client.get_state_commitment();
    assert_eq!(c.len(), 48, "commitment must be exactly 48 bytes");
}

#[test]
fn commitment_has_protocol_prefix() {
    let (env, client, admin, service) = initialized();
    let c = client.get_state_commitment();
    let arr = c.to_array();
    // First 16 bytes = b"LEDGERLENS_KZG_1"
    let expected_prefix = b"LEDGERLENS_KZG_1";
    assert_eq!(
        &arr[..16],
        expected_prefix,
        "commitment must carry the LEDGERLENS_KZG_1 protocol prefix"
    );
}

#[test]
fn commitment_changes_after_score_write() {
    let (env, client, admin, service) = initialized();

    let before = client.get_state_commitment();
    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");
    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &50,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let after = client.get_state_commitment();
    assert_ne!(
        before.to_array(),
        after.to_array(),
        "commitment must change after a score write"
    );
}

#[test]
fn commitment_changes_on_score_update() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &30,
            &false,
            &false,
            &1,
            &80,
            &1,
            &None,
        );
    let c1 = client.get_state_commitment();

    // Advance past cooldown.
    env.ledger().with_mut(|l| l.timestamp += 3_601);

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &70,
            &false,
            &false,
            &3_602,
            &90,
            &1,
            &None,
        );
    let c2 = client.get_state_commitment();

    assert_ne!(
        c1.to_array(),
        c2.to_array(),
        "commitment must change when a score is updated"
    );
}

// ── Membership proof tests ───────────────────────────────────────────────────

#[test]
fn membership_proof_is_97_bytes() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");
    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &42,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let proof = client.get_membership_proof(&wallet, &pair);
    assert_eq!(proof.len(), 97, "proof must be exactly 97 bytes");
}

#[test]
fn membership_proof_type_byte_is_member() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");
    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &42,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let proof = client.get_membership_proof(&wallet, &pair);
    let arr = proof_to_array(&proof);
    assert_eq!(arr[0], 0x01, "proof type byte must be 0x01 (member)");
}

#[test]
fn verify_membership_returns_true_for_valid_proof() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");
    let score: u32 = 42;

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &score,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let commitment = client.get_state_commitment();
    let proof = client.get_membership_proof(&wallet, &pair);
    let timestamp = client.get_score(&wallet, &pair).timestamp;

    // Membership proof must verify with the correct score.
    assert!(
        client.verify_membership(&commitment, &wallet, &pair, &score, &timestamp, &proof),
        "valid membership proof must verify"
    );
}

#[test]
fn verify_membership_fails_for_wrong_score() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &42,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let commitment = client.get_state_commitment();
    let proof = client.get_membership_proof(&wallet, &pair);
    let timestamp = client.get_score(&wallet, &pair).timestamp;

    // Wrong score with the correct timestamp must fail: v is bound to
    // (score, timestamp), so a mismatched score changes the recomputed v.
    assert!(
        !client.verify_membership(&commitment, &wallet, &pair, &99, &timestamp, &proof),
        "proof must not verify for a different score"
    );

    // Wrong wallet must also fail (key binding via z).
    let wrong_wallet = Address::generate(&env);
    assert!(
        !client.verify_membership(&commitment, &wrong_wallet, &pair, &42, &timestamp, &proof),
        "proof must not verify for a different wallet"
    );
}

#[test]
fn verify_membership_fails_for_wrong_pair() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");
    let other_pair = symbol_short!("BTC_USDC");

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &42,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let commitment = client.get_state_commitment();
    let proof = client.get_membership_proof(&wallet, &pair);
    let timestamp = client.get_score(&wallet, &pair).timestamp;

    assert!(
        !client.verify_membership(&commitment, &wallet, &other_pair, &42, &timestamp, &proof),
        "proof must not verify for a different asset pair"
    );
}

#[test]
fn verify_membership_fails_for_tampered_proof() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &42,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let commitment = client.get_state_commitment();
    let proof = client.get_membership_proof(&wallet, &pair);
    let timestamp = client.get_score(&wallet, &pair).timestamp;

    // Flip the last byte of the witness.
    let mut arr = proof_to_array(&proof);
    arr[96] ^= 0xFF;
    let tampered = Bytes::from_array(&env, &arr);

    assert!(
        !client.verify_membership(&commitment, &wallet, &pair, &42, &timestamp, &tampered),
        "tampered proof witness must not verify"
    );
}

#[test]
fn verify_membership_fails_for_stale_commitment() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &42,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    // Snapshot commitment and proof BEFORE the update.
    let old_commitment = client.get_state_commitment();
    let old_proof = client.get_membership_proof(&wallet, &pair);
    let old_timestamp = client.get_score(&wallet, &pair).timestamp;

    // Update the score (past cooldown).
    env.ledger().with_mut(|l| l.timestamp += 3_601);
    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &75,
            &false,
            &false,
            &3_602,
            &90,
            &1,
            &None,
        );

    // A new proof against the new commitment should work.
    let new_commitment = client.get_state_commitment();
    let new_proof = client.get_membership_proof(&wallet, &pair);
    let new_timestamp = client.get_score(&wallet, &pair).timestamp;
    assert!(client.verify_membership(&new_commitment, &wallet, &pair, &75, &new_timestamp, &new_proof));

    // Old proof against new commitment must fail (commitment changed).
    assert!(
        !client.verify_membership(&new_commitment, &wallet, &pair, &42, &old_timestamp, &old_proof),
        "old proof must not verify against new commitment"
    );

    // Old proof against old commitment still verifies (snapshot integrity).
    assert!(
        client.verify_membership(&old_commitment, &wallet, &pair, &42, &old_timestamp, &old_proof),
        "old proof must still verify against the old commitment snapshot"
    );
}

// ── Non-membership proof tests ───────────────────────────────────────────────

#[test]
fn nonmember_proof_type_byte_is_nonmember() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    // No score submitted — wallet has no entry.
    let proof = client.get_membership_proof(&wallet, &pair);
    assert_eq!(proof.len(), 97);
    let arr = proof_to_array(&proof);
    assert_eq!(arr[0], 0x02, "proof type byte must be 0x02 (non-member)");
}

#[test]
fn nonmember_proof_v_is_all_zeros() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    let proof = client.get_membership_proof(&wallet, &pair);
    let arr = proof_to_array(&proof);
    // v occupies bytes [33..65] — must be all-zeros sentinel.
    assert_eq!(
        &arr[33..65],
        &[0u8; 32],
        "non-member proof v must be the all-zeros sentinel"
    );
}

#[test]
fn verify_membership_with_score_zero_accepts_nonmember_proof() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    // No score — get non-membership proof.
    let commitment = client.get_state_commitment();
    let proof = client.get_membership_proof(&wallet, &pair);

    assert!(
        client.verify_membership(&commitment, &wallet, &pair, &0, &0, &proof),
        "non-membership proof must verify when score=0"
    );
}

#[test]
fn verify_membership_with_nonzero_score_rejects_nonmember_proof() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    let commitment = client.get_state_commitment();
    let proof = client.get_membership_proof(&wallet, &pair);

    // Passing a non-zero score with a non-member proof must fail.
    assert!(
        !client.verify_membership(&commitment, &wallet, &pair, &1, &0, &proof),
        "non-membership proof must not accept non-zero score"
    );
}

#[test]
fn nonmember_proof_fails_for_different_wallet() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let other_wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    let commitment = client.get_state_commitment();
    // Proof for wallet
    let proof = client.get_membership_proof(&wallet, &pair);

    // Presenting wallet's non-member proof as proof for other_wallet must fail.
    assert!(
        !client.verify_membership(&commitment, &other_wallet, &pair, &0, &0, &proof),
        "non-member proof must not verify for a different wallet"
    );
}

// ── Multiple entries tests ───────────────────────────────────────────────────

#[test]
fn commitment_reflects_multiple_independent_entries() {
    let (env, client, admin, service) = initialized();

    let pair = symbol_short!("XLMUSDC");
    let wallet_a = Address::generate(&env);
    let wallet_b = Address::generate(&env);

    client
        .submit_score(
            &Vec::new(&env),
            &wallet_a,
            &pair,
            &20,
            &false,
            &false,
            &1,
            &80,
            &1,
            &None,
        );
    let c1 = client.get_state_commitment();

    client
        .submit_score(
            &Vec::new(&env),
            &wallet_b,
            &pair,
            &80,
            &true,
            &false,
            &2,
            &90,
            &1,
            &None,
        );
    let c2 = client.get_state_commitment();

    // Commitment must have changed again.
    assert_ne!(c1.to_array(), c2.to_array());

    // Both wallets must produce valid membership proofs against c2.
    let proof_a = client.get_membership_proof(&wallet_a, &pair);
    let proof_b = client.get_membership_proof(&wallet_b, &pair);
    let timestamp_a = client.get_score(&wallet_a, &pair).timestamp;
    let timestamp_b = client.get_score(&wallet_b, &pair).timestamp;

    assert!(
        client.verify_membership(&c2, &wallet_a, &pair, &20, &timestamp_a, &proof_a),
        "wallet_a membership proof must verify against latest commitment"
    );
    assert!(
        client.verify_membership(&c2, &wallet_b, &pair, &80, &timestamp_b, &proof_b),
        "wallet_b membership proof must verify against latest commitment"
    );
}

#[test]
fn nonmember_proof_for_unknown_pair_works_alongside_known_entries() {
    let (env, client, admin, service) = initialized();

    let pair = symbol_short!("XLMUSDC");
    let absent_pair = symbol_short!("ETH_USDC");
    let wallet = Address::generate(&env);

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &55,
            &false,
            &false,
            &1,
            &85,
            &1,
            &None,
        );

    let commitment = client.get_state_commitment();

    // Non-member proof for the absent pair.
    let proof = client.get_membership_proof(&wallet, &absent_pair);
    let arr = proof_to_array(&proof);
    assert_eq!(arr[0], 0x02, "should be non-member proof");

    assert!(
        client.verify_membership(&commitment, &wallet, &absent_pair, &0, &0, &proof),
        "non-member proof for absent pair must verify"
    );

    // The existing pair's membership proof must still hold.
    let member_proof = client.get_membership_proof(&wallet, &pair);
    let member_timestamp = client.get_score(&wallet, &pair).timestamp;
    assert!(
        client.verify_membership(&commitment, &wallet, &pair, &55, &member_timestamp, &member_proof),
        "member proof must still verify alongside non-member proof"
    );
}

// ── Batch submission path tests ──────────────────────────────────────────────

#[test]
fn batch_submission_updates_commitment() {
    let (env, client, admin, service) = initialized();

    let pair = symbol_short!("XLMUSDC");
    let wallet1 = Address::generate(&env);
    let wallet2 = Address::generate(&env);

    let before = client.get_state_commitment();

    let mut batch = Vec::new(&env);
    batch.push_back(ScoreSubmission {
        wallet: wallet1.clone(),
        asset_pair: pair.clone(),
        score: 30,
        benford_flag: false,
        ml_flag: false,
        timestamp: 100,
        confidence: 80,
        model_version: 1,
    });
    batch.push_back(ScoreSubmission {
        wallet: wallet2.clone(),
        asset_pair: pair.clone(),
        score: 70,
        benford_flag: true,
        ml_flag: false,
        timestamp: 200,
        confidence: 90,
        model_version: 1,
    });

    let result = client.submit_scores_batch(&batch);
    assert_eq!(result.accepted_count, 2);

    let after = client.get_state_commitment();
    assert_ne!(before.to_array(), after.to_array(), "batch must update commitment");

    // Both entries must be provable.
    let proof1 = client.get_membership_proof(&wallet1, &pair);
    let proof2 = client.get_membership_proof(&wallet2, &pair);
    let timestamp1 = client.get_score(&wallet1, &pair).timestamp;
    let timestamp2 = client.get_score(&wallet2, &pair).timestamp;

    assert!(client.verify_membership(&after, &wallet1, &pair, &30, &timestamp1, &proof1));
    assert!(client.verify_membership(&after, &wallet2, &pair, &70, &timestamp2, &proof2));
}

// ── Proof format edge cases ──────────────────────────────────────────────────

#[test]
fn verify_membership_returns_false_for_empty_proof() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &42,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let commitment = client.get_state_commitment();
    let timestamp = client.get_score(&wallet, &pair).timestamp;
    let empty = Bytes::new(&env);

    assert!(
        !client.verify_membership(&commitment, &wallet, &pair, &42, &timestamp, &empty),
        "empty proof bytes must not verify"
    );
}

#[test]
fn verify_membership_returns_false_for_wrong_commitment_prefix() {
    let (env, client, admin, service) = initialized();

    let wallet = Address::generate(&env);
    let pair = symbol_short!("XLMUSDC");

    client
        .submit_score(
            &Vec::new(&env),
            &wallet,
            &pair,
            &42,
            &false,
            &false,
            &1,
            &90,
            &1,
            &None,
        );

    let proof = client.get_membership_proof(&wallet, &pair);
    let commitment = client.get_state_commitment();
    let timestamp = client.get_score(&wallet, &pair).timestamp;

    // Corrupt the prefix of the commitment.
    let mut arr = commitment.to_array();
    arr[0] ^= 0xFF;
    let bad_commitment = BytesN::<48>::from_array(&env, &arr);

    assert!(
        !client.verify_membership(&bad_commitment, &wallet, &pair, &42, &timestamp, &proof),
        "corrupt commitment prefix must cause verify to return false"
    );
}

// ── Range proof helper (off-chain pattern) ───────────────────────────────────
//
// Range proofs are validated off-chain by collecting per-entry membership
// proofs and checking each. We demonstrate the pattern in-test to verify
// the API contract: "all scores for pair P with wallet_a and wallet_b are < 80".

#[test]
fn range_proof_all_scores_below_80() {
    let (env, client, admin, service) = initialized();

    let pair = symbol_short!("XLMUSDC");
    let wallets = [
        Address::generate(&env),
        Address::generate(&env),
        Address::generate(&env),
    ];
    let scores = [10u32, 45u32, 79u32];

    for (w, s) in wallets.iter().zip(scores.iter()) {
        client
            .submit_score(
                &Vec::new(&env),
                w,
                &pair,
                s,
                &false,
                &false,
                &1,
                &80,
                &1,
                &None,
            );
        // Advance past cooldown so each submission is accepted.
        env.ledger().with_mut(|l| l.timestamp += 3_601);
    }

    let commitment = client.get_state_commitment();

    // Collect and verify all membership proofs; check score bound.
    let mut all_below_80 = true;
    for (w, _s) in wallets.iter().zip(scores.iter()) {
        let proof = client.get_membership_proof(w, &pair);
        let arr = proof_to_array(&proof);
        assert_eq!(arr[0], 0x01, "expected member proof for each wallet");

        // True range check: verify with each score value — all must pass
        // for each wallet, and each known score must be < 80.
        let actual_score_entry = client.get_score(w, &pair);
        assert!(
            actual_score_entry.score < 80,
            "all scores in the range proof must be below 80"
        );
        // Membership proof is valid.
        assert!(
            client.verify_membership(
                &commitment,
                w,
                &pair,
                &actual_score_entry.score,
                &actual_score_entry.timestamp,
                &proof
            ),
            "membership proof must verify for range proof participant"
        );

        if actual_score_entry.score >= 80 {
            all_below_80 = false;
        }
    }

    assert!(all_below_80, "range claim 'all < 80' must hold");
}

// ── Pure verkle primitive tests (catch mutants in verkle.rs) ───────────────

#[test]
fn test_xor32_commutative() {
    let a = [1u8; 32];
    let b = [2u8; 32];
    let ab = xor32(&a, &b);
    let ba = xor32(&b, &a);
    assert_eq!(ab, ba, "xor32 must be commutative");
}

#[test]
fn test_xor32_identity() {
    let a = [0xABu8; 32];
    let zero = [0u8; 32];
    assert_eq!(xor32(&a, &zero), a, "a XOR 0 == a");
}

#[test]
fn test_xor32_self_inverse() {
    let a = [0xABu8; 32];
    let zero = [0u8; 32];
    assert_eq!(xor32(&a, &a), zero, "a XOR a == 0");
}

#[test]
fn test_derive_evaluation_point_deterministic() {
    let env = Env::default();
    let wallet_bytes = [3u8; 56];
    let pair_bytes = [4u8; 9];
    let z1 = derive_evaluation_point(&env, &wallet_bytes, &pair_bytes);
    let z2 = derive_evaluation_point(&env, &wallet_bytes, &pair_bytes);
    assert_eq!(z1, z2, "derive_evaluation_point must be deterministic");
}

#[test]
fn test_derive_evaluation_point_differs_for_diff_inputs() {
    let env = Env::default();
    let wallet_a = [1u8; 56];
    let wallet_b = [2u8; 56];
    let pair = [3u8; 9];
    let za = derive_evaluation_point(&env, &wallet_a, &pair);
    let zb = derive_evaluation_point(&env, &wallet_b, &pair);
    assert_ne!(za, zb, "different wallets must produce different z");
}

#[test]
fn test_derive_value_element_deterministic() {
    let env = Env::default();
    let z = [5u8; 32];
    let v1 = derive_value_element(&env, 42, 1000, &z);
    let v2 = derive_value_element(&env, 42, 1000, &z);
    assert_eq!(v1, v2, "derive_value_element must be deterministic");
}

#[test]
fn test_derive_value_element_differs_for_diff_scores() {
    let env = Env::default();
    let z = [5u8; 32];
    let v1 = derive_value_element(&env, 42, 1000, &z);
    let v2 = derive_value_element(&env, 99, 1000, &z);
    assert_ne!(v1, v2, "different scores must produce different v");
}

#[test]
fn test_hash_leaf_deterministic() {
    let env = Env::default();
    let z = [6u8; 32];
    let v = [7u8; 32];
    let h1 = hash_leaf(&env, &z, &v);
    let h2 = hash_leaf(&env, &z, &v);
    assert_eq!(h1, h2, "hash_leaf must be deterministic");
}

#[test]
fn test_encode_decode_roundtrip_member() {
    let env = Env::default();
    let z = [8u8; 32];
    let v = [9u8; 32];
    let witness = [10u8; 32];
    let encoded = encode_proof(&env, true, &z, &v, &witness);
    let decoded = decode_proof(&encoded);
    assert!(decoded.is_some(), "decode must succeed for valid proof");
    let (is_member, dz, dv, dw) = decoded.unwrap();
    assert!(is_member, "round-tripped is_member must be true");
    assert_eq!(dz, z, "round-tripped z must match");
    assert_eq!(dv, v, "round-tripped v must match");
    assert_eq!(dw, witness, "round-tripped witness must match");
}

#[test]
fn test_encode_decode_roundtrip_nonmember() {
    let env = Env::default();
    let z = [11u8; 32];
    let v = [0u8; 32];
    let witness = [12u8; 32];
    let encoded = encode_proof(&env, false, &z, &v, &witness);
    let decoded = decode_proof(&encoded);
    assert!(decoded.is_some(), "decode must succeed for non-member proof");
    let (is_member, _dz, _dv, _dw) = decoded.unwrap();
    assert!(!is_member, "round-tripped is_member must be false");
}

#[test]
fn test_decode_fails_for_short_input() {
    let env = Env::default();
    let short = Bytes::from_array(&env, &[1u8, 2u8]);
    assert!(decode_proof(&short).is_none(), "decode must fail for too-short input");
}

#[test]
fn test_commitment_bytes48_roundtrip() {
    let env = Env::default();
    let commit = [13u8; 32];
    let b48 = commitment_to_bytes48(&env, &commit);
    let decoded = bytes48_to_commitment(&b48);
    assert!(decoded.is_some(), "bytes48_to_commitment must succeed for valid prefix");
    assert_eq!(decoded.unwrap(), commit, "round-tripped commitment must match");
}

#[test]
fn test_commitment_bytes48_prefix_check() {
    let env = Env::default();
    // A 48-byte array without the correct prefix should be rejected.
    let bad = BytesN::<48>::from_array(&env, &[0xFFu8; 48]);
    assert!(bytes48_to_commitment(&bad).is_none(), "must reject missing prefix");
}

#[test]
fn test_verify_proof_with_bogus_witness() {
    let env = Env::default();
    let commitment = [0u8; 32];
    let z = [14u8; 32];
    let v = [15u8; 32];
    let bogus_witness = [16u8; 32];
    // A random witness should not verify against empty commitment.
    assert!(
        !verify_proof(&env, &commitment, &z, &v, &bogus_witness),
        "bogus witness must not verify"
    );
}

#[test]
fn test_update_commitment_is_deterministic() {
    let env = Env::default();
    let prev = [17u8; 32];
    let z = [18u8; 32];
    let v = [19u8; 32];
    let c1 = verkle::update_commitment(&env, &prev, &z, &v);
    let c2 = verkle::update_commitment(&env, &prev, &z, &v);
    assert_eq!(c1, c2, "update_commitment must be deterministic");
}

#[test]
fn test_update_commitment_different_z_different_result() {
    let env = Env::default();
    let prev = [20u8; 32];
    let v = [22u8; 32];
    let z1 = [21u8; 32];
    let z2 = [23u8; 32];
    let c1 = verkle::update_commitment(&env, &prev, &z1, &v);
    let c2 = verkle::update_commitment(&env, &prev, &z2, &v);
    assert_ne!(c1, c2, "different z must produce different commitments");
}
