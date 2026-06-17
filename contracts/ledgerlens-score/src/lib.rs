#![no_std]
#![allow(deprecated)] // Required: contractimpl macro calls spec_xdr_* for all fns including deprecated ones

mod constants;
mod errors;
mod events;
mod storage;
mod types;

#[cfg(test)]
mod test;

#[cfg(test)]
mod test_upgrade;

#[cfg(test)]
mod test_interface;

use soroban_sdk::{contract, contractimpl, symbol_short, Address, BytesN, Env, Symbol, Vec};

pub use errors::Error;
pub use types::{AggregateRiskScore, RiskScore, ScoreSubmission, UpgradeProposal};

/// On-chain truth layer for LedgerLens risk scores.
///
/// The off-chain detection pipeline (Benford's Law engine + ML ensemble)
/// computes a 0-100 risk score per wallet / asset-pair and writes it here
/// via `submit_score`.  Any Soroban contract can then call `get_score` to
/// gate suspicious activity without relying on an external oracle.
#[contract]
pub struct LedgerLensScoreContract;

#[contractimpl]
impl LedgerLensScoreContract {
    // ── Lifecycle ────────────────────────────────────────────────────────────

    /// One-time setup.  `admin` can rotate the scoring service address
    /// and manage contract-wide configuration; `service` is the off-chain
    /// LedgerLens account authorised to submit scores.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// # use soroban_sdk::symbol_short;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// assert_eq!(client.get_admin(), admin);
    /// assert_eq!(client.get_service(), service);
    /// ```
    pub fn initialize(env: Env, admin: Address, service: Address) -> Result<(), Error> {
        if storage::has_admin(&env) {
            return Err(Error::AlreadyInitialized);
        }
        storage::set_admin(&env, &admin);
        storage::set_service(&env, &service);
        Ok(())
    }

    /// Returns the baked-in ABI version of this contract build.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// assert_eq!(client.get_version(), 1);
    /// ```
    pub fn get_version(env: Env) -> u32 {
        storage::get_contract_version(&env)
    }

    // ── Score submission ─────────────────────────────────────────────────────

    /// Register a freshly computed risk score for `wallet` / `asset_pair`.
    ///
    /// When a multi-sig service set has been configured (via
    /// `add_service_signer` / `set_service_threshold`), `signers` must
    /// contain at least `ServiceThreshold` addresses, each of which must be
    /// a member of `ServiceSet`.  Each listed signer must individually
    /// authorize the transaction via Soroban's native `require_auth`.
    ///
    /// When no multi-sig set has been configured (legacy mode) the function
    /// falls back to the original single-service authorization path.
    ///
    /// Returns `ContractPaused` if the admin has activated the circuit breaker.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// # use soroban_sdk::symbol_short;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let wallet = Address::generate(&env);
    /// let asset_pair = symbol_short!("XLM_USDC");
    /// client.submit_score(&wallet, &asset_pair, &42, &true, &false, &1, &90, &1).unwrap();
    /// let score = client.get_score(&wallet, &asset_pair).unwrap();
    /// assert_eq!(score.score, 42);
    /// assert!(score.benford_flag);
    /// ```
    #[allow(clippy::too_many_arguments)]
    pub fn submit_score(
        env: Env,
        signers: Vec<Address>,
        wallet: Address,
        asset_pair: Symbol,
        score: u32,
        benford_flag: bool,
        ml_flag: bool,
        timestamp: u64,
        confidence: u32,
        model_version: u32,
    ) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        if storage::is_paused(&env) {
            return Err(Error::ContractPaused);
        }

        let service_set = storage::get_service_set(&env);
        let threshold = storage::get_service_threshold(&env);

        if !service_set.is_empty() && threshold > 0 {
            // Multi-sig path: verify count, membership, then require_auth each.
            if signers.len() < threshold {
                return Err(Error::InsufficientSigners);
            }
            for i in 0..signers.len() {
                let signer = signers.get(i).unwrap();
                if !service_set.contains(&signer) {
                    return Err(Error::UnauthorizedSigner);
                }
                signer.require_auth();
            }
        } else {
            // Legacy single-service path.
            let service = storage::get_service(&env);
            service.require_auth();
        }

        if score > 100 {
            return Err(Error::InvalidScore);
        }
        if confidence > 100 {
            return Err(Error::InvalidConfidence);
        }

        let risk_score =
            RiskScore { score, benford_flag, ml_flag, timestamp, confidence, model_version };

        storage::set_score(&env, &wallet, &asset_pair, &risk_score);
        storage::push_score_history(&env, &wallet, &asset_pair, &risk_score);
        storage::register_pair_for_wallet(&env, &wallet, &asset_pair);
        Self::refresh_aggregate_cache(&env, &wallet);

        let score_threshold = storage::get_risk_threshold(&env);
        if score >= score_threshold {
            events::threshold_breached(&env, &wallet, &asset_pair, score, score_threshold);
        }

        events::score_submitted(&env, &wallet, &asset_pair, &risk_score);
        Ok(())
    }

    /// Submit multiple risk scores in a single invocation.  The service
    /// account authorises once for the whole batch.  Entries with
    /// out-of-range `score` or `confidence` are silently skipped; the
    /// function returns the count of successfully written entries.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::{LedgerLensScoreContract, LedgerLensScoreContractClient, ScoreSubmission};
    /// # use soroban_sdk::{testutils::Address as _, Env, Address, Vec};
    /// # use soroban_sdk::symbol_short;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let wallet1 = Address::generate(&env);
    /// let wallet2 = Address::generate(&env);
    /// let asset_pair = symbol_short!("XLM_USDC");
    /// let mut batch: Vec<ScoreSubmission> = Vec::new(&env);
    /// batch.push_back(ScoreSubmission { wallet: wallet1.clone(), asset_pair: asset_pair.clone(), score: 45, benford_flag: false, ml_flag: false, timestamp: 1000, confidence: 80, model_version: 2 });
    /// batch.push_back(ScoreSubmission { wallet: wallet2.clone(), asset_pair: asset_pair.clone(), score: 85, benford_flag: true, ml_flag: true, timestamp: 2000, confidence: 90, model_version: 2 });
    /// let accepted = client.submit_scores_batch(&batch);
    /// assert_eq!(accepted, 2);
    /// assert_eq!(client.get_score(&wallet1, &asset_pair).unwrap().score, 45);
    /// assert_eq!(client.get_score(&wallet2, &asset_pair).unwrap().score, 85);
    /// ```
    pub fn submit_scores_batch(env: Env, submissions: Vec<ScoreSubmission>) -> Result<u32, Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        if storage::is_paused(&env) {
            return Err(Error::ContractPaused);
        }

        let service = storage::get_service(&env);
        service.require_auth();

        if submissions.is_empty() {
            return Err(Error::EmptyBatch);
        }
        if submissions.len() > constants::MAX_BATCH_SIZE {
            return Err(Error::BatchTooLarge);
        }

        let threshold = storage::get_risk_threshold(&env);
        let mut accepted: u32 = 0;

        for i in 0..submissions.len() {
            let sub = submissions.get(i).unwrap();

            if sub.score > 100 || sub.confidence > 100 {
                continue;
            }

            let risk_score = RiskScore {
                score: sub.score,
                benford_flag: sub.benford_flag,
                ml_flag: sub.ml_flag,
                timestamp: sub.timestamp,
                confidence: sub.confidence,
                model_version: sub.model_version,
            };

            storage::set_score(&env, &sub.wallet, &sub.asset_pair, &risk_score);
            storage::push_score_history(&env, &sub.wallet, &sub.asset_pair, &risk_score);
            storage::register_pair_for_wallet(&env, &sub.wallet, &sub.asset_pair);
            Self::refresh_aggregate_cache(&env, &sub.wallet);

            if sub.score >= threshold {
                events::threshold_breached(
                    &env,
                    &sub.wallet,
                    &sub.asset_pair,
                    sub.score,
                    threshold,
                );
            }

            events::score_submitted(&env, &sub.wallet, &sub.asset_pair, &risk_score);
            accepted += 1;
        }

        Ok(accepted)
    }

    // ── Score retrieval ──────────────────────────────────────────────────────

    /// Read-only lookup of the latest risk score for `wallet` / `asset_pair`.
    /// Callable by any account or contract.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// # use soroban_sdk::symbol_short;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let wallet = Address::generate(&env);
    /// let asset_pair = symbol_short!("XLM_USDC");
    /// client.submit_score(&wallet, &asset_pair, &10, &false, &false, &1, &50, &1).unwrap();
    /// let score = client.get_score(&wallet, &asset_pair);
    /// assert_eq!(score.score, 10);
    /// ```
    pub fn get_score(env: Env, wallet: Address, asset_pair: Symbol) -> Result<RiskScore, Error> {
        storage::get_score(&env, &wallet, &asset_pair).ok_or(Error::ScoreNotFound)
    }

    /// Returns the ordered history of the last `HISTORY_MAX_DEPTH` risk scores
    /// for `wallet` / `asset_pair`, oldest first.  Returns an empty Vec when no
    /// scores have been submitted yet.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// # use soroban_sdk::symbol_short;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let wallet = Address::generate(&env);
    /// let asset_pair = symbol_short!("XLM_USDC");
    /// client.submit_score(&wallet, &asset_pair, &10, &false, &false, &1, &50, &1).unwrap();
    /// client.submit_score(&wallet, &asset_pair, &20, &false, &false, &2, &60, &1).unwrap();
    /// let history = client.get_score_history(&wallet, &asset_pair);
    /// assert_eq!(history.len(), 2);
    /// assert_eq!(history.get(0).unwrap().score, 10);
    /// assert_eq!(history.get(1).unwrap().score, 20);
    /// ```
    pub fn get_score_history(env: Env, wallet: Address, asset_pair: Symbol) -> Vec<RiskScore> {
        storage::get_score_history(&env, &wallet, &asset_pair)
    }

    // ── Cross-asset aggregate risk ───────────────────────────────────────────

    /// Computes `wallet`'s cross-asset aggregate risk score: a weighted
    /// average over every asset pair the wallet has a `RiskScore` for.
    ///
    /// ```text
    /// aggregate_score = Σ (pair_weight[i] * pair_score[i]) / Σ pair_weight[i]
    /// ```
    ///
    /// `pair_weight[i]` defaults to `1` (an unweighted average) unless the
    /// admin has configured one via `set_pair_weight`. A pair with weight
    /// `0` still contributes to `pair_count`, `max_pair_score`,
    /// `benford_flag_count`, `ml_flag_count`, and `last_updated`, but is
    /// excluded from the weighted-average numerator and denominator.
    ///
    /// This function always recomputes from the live per-pair scores
    /// stored under `AssetPairs(wallet)` — it never reads the
    /// `AggregateScore(wallet)` cache that `submit_score` /
    /// `submit_scores_batch` refresh as a side effect, so the result is
    /// always consistent with the latest submissions.
    ///
    /// Complexity is O(N) in the number of distinct pairs the wallet has
    /// a score for. The contract does not enforce a hard cap on N, but the
    /// aggregate engine is designed around [`constants::MAX_WALLET_PAIRS`]
    /// (currently 20) as the expected practical maximum.
    ///
    /// Returns [`Error::ScoreNotFound`] if the wallet has no scores, or if
    /// every registered pair currently has a weight of `0` (an undefined
    /// average). Returns [`Error::ArithmeticOverflow`] if the weighted sum
    /// would overflow — this can only happen with extreme admin-configured
    /// weights, since per-pair scores are bounded to 0-100.
    pub fn get_aggregate_score(env: Env, wallet: Address) -> Result<AggregateRiskScore, Error> {
        Self::compute_aggregate_score(&env, &wallet)
    }

    /// Sets the weight used for `asset_pair` in the aggregate risk
    /// computation. A weight of `0` excludes the pair from the weighted
    /// average's denominator entirely. Admin only.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// # use soroban_sdk::symbol_short;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let pair = symbol_short!("XLM_USDC");
    /// client.set_pair_weight(&pair, &3).unwrap();
    /// assert_eq!(client.get_pair_weight(&pair), 3);
    /// ```
    pub fn set_pair_weight(env: Env, asset_pair: Symbol, weight: u32) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        storage::get_admin(&env).require_auth();
        storage::set_pair_weight(&env, &asset_pair, weight);
        events::pair_weight_updated(&env, &asset_pair, weight);
        Ok(())
    }

    /// Returns the configured weight for `asset_pair`. Defaults to `1`
    /// (simple average) until the admin sets one explicitly.
    pub fn get_pair_weight(env: Env, asset_pair: Symbol) -> u32 {
        storage::get_pair_weight(&env, &asset_pair)
    }

    // ── Composability interface (stable ABI) ─────────────────────────────────
    //
    // The functions below form the `ILedgerLensScore` composability surface
    // documented in `docs/interface-spec.md`. They are the canonical,
    // version-stable integration point for third-party Soroban protocols
    // (AMMs, lending markets, DEX aggregators). Their signatures and
    // semantics are covered by the interface stability guarantees in that
    // spec — do not change them without bumping `CONTRACT_VERSION` and the
    // interface version, and announcing a breaking change.

    /// Infallible cross-contract risk gate.
    ///
    /// Returns `true` when the wallet's latest risk score for `asset_pair`
    /// is **strictly below** `gate_threshold` — i.e. the wallet is considered
    /// safe to proceed. Returns `false` when:
    ///
    /// * the score is `>= gate_threshold` (too risky), **or**
    /// * no score exists for the `(wallet, asset_pair)` pair.
    ///
    /// The "no score" case deliberately returns `false` (the *conservative*
    /// default): an integrating protocol should treat wallets it has no
    /// information about as potentially risky rather than waving them through.
    ///
    /// This function is **infallible** (returns `bool`, never `Result`) and
    /// **side-effect free** — it performs a pure read that does not even
    /// extend storage TTL. It is designed to be called directly from inside
    /// another contract's authorization / guard logic: it can never panic and
    /// can never propagate an `Error` back into the caller, so it cannot be
    /// used to grief the calling protocol's gas or disable its security guard.
    ///
    /// # Example (caller side)
    ///
    /// ```ignore
    /// let client = LedgerLensScoreContractClient::new(&env, &llens_id);
    /// if !client.query_risk_gate(&user, &symbol_short!("XLM_USDC"), &75) {
    ///     return Err(MyError::HighRiskWallet);
    /// }
    /// ```
    pub fn query_risk_gate(
        env: Env,
        wallet: Address,
        asset_pair: Symbol,
        gate_threshold: u32,
    ) -> bool {
        match storage::peek_score(&env, &wallet, &asset_pair) {
            Some(risk) => risk.score < gate_threshold,
            None => false,
        }
    }

    /// Capability-detection registry for the composability interface.
    ///
    /// Returns `true` if this contract build supports the named `capability`,
    /// allowing cross-contract callers to feature-detect at runtime instead of
    /// hardcoding contract version numbers. The capability symbols are part of
    /// the stable ABI: removing one is a breaking change.
    ///
    /// Recognised capabilities:
    ///
    /// | Symbol      | Backing functionality                              |
    /// |-------------|----------------------------------------------------|
    /// | `score`     | `get_score` / `submit_score`                       |
    /// | `history`   | `get_score_history`                                |
    /// | `batch`     | `submit_scores_batch`                              |
    /// | `gate`      | `query_risk_gate`                                  |
    /// | `aggr`      | `get_aggregate_score` (cross-asset aggregate risk) |
    ///
    /// Any unrecognised `capability` returns `false`.
    pub fn supports_interface(_env: Env, capability: Symbol) -> bool {
        capability == symbol_short!("score")
            || capability == symbol_short!("history")
            || capability == symbol_short!("batch")
            || capability == symbol_short!("gate")
            || capability == symbol_short!("aggr")
    }

    // ── Service management ───────────────────────────────────────────────────

    /// Add `signer` to the M-of-N service signer set.  Admin only.
    ///
    /// Returns [`Error::ServiceSetFull`] when the set already contains
    /// `MAX_SERVICE_SIGNERS` members, [`Error::SignerAlreadyInSet`] when
    /// `signer` is already present.
    pub fn add_service_signer(env: Env, signer: Address) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        storage::get_admin(&env).require_auth();

        let mut set = storage::get_service_set(&env);
        if set.len() >= constants::MAX_SERVICE_SIGNERS {
            return Err(Error::ServiceSetFull);
        }
        if set.contains(&signer) {
            return Err(Error::SignerAlreadyInSet);
        }
        set.push_back(signer.clone());
        storage::set_service_set(&env, &set);
        events::signer_added(&env, &signer);
        Ok(())
    }

    /// Remove `signer` from the M-of-N service signer set.  Admin only.
    ///
    /// Returns [`Error::SignerNotInSet`] when `signer` is not in the set.
    /// If removing the signer would make the set smaller than the current
    /// threshold, the threshold is automatically reduced to the new set size.
    pub fn remove_service_signer(env: Env, signer: Address) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        storage::get_admin(&env).require_auth();

        let mut set = storage::get_service_set(&env);
        let pos = set.first_index_of(&signer);
        let idx = pos.ok_or(Error::SignerNotInSet)?;
        set.remove(idx);
        storage::set_service_set(&env, &set);

        // Auto-adjust threshold if it now exceeds the reduced set size.
        let threshold = storage::get_service_threshold(&env);
        if set.is_empty() {
            storage::set_service_threshold(&env, 0);
            events::service_threshold_updated(&env, 0);
        } else if threshold > set.len() {
            storage::set_service_threshold(&env, set.len());
            events::service_threshold_updated(&env, set.len());
        }

        events::signer_removed(&env, &signer);
        Ok(())
    }

    /// Set the signing threshold M.  Admin only.
    ///
    /// Returns [`Error::InvalidThreshold`] when `threshold` is `0` or exceeds
    /// the current service-set size.
    pub fn set_service_threshold(env: Env, threshold: u32) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        storage::get_admin(&env).require_auth();

        let set = storage::get_service_set(&env);
        if threshold == 0 || threshold > set.len() {
            return Err(Error::InvalidThreshold);
        }
        storage::set_service_threshold(&env, threshold);
        events::service_threshold_updated(&env, threshold);
        Ok(())
    }

    /// Returns the current M-of-N service signer set.
    pub fn get_service_signers(env: Env) -> Vec<Address> {
        storage::get_service_set(&env)
    }

    /// Returns the current signing threshold.
    pub fn get_service_threshold(env: Env) -> u32 {
        storage::get_service_threshold(&env)
    }

    /// Rotate the authorised off-chain scoring service address.  Admin only.
    ///
    /// # Deprecation notice
    ///
    /// This function is deprecated in favour of the M-of-N multi-signature
    /// model (`add_service_signer` / `set_service_threshold`).  It is
    /// preserved for backward compatibility and will be removed in a future
    /// major release.  New integrations should use the multisig functions.
    #[deprecated(note = "Use add_service_signer / set_service_threshold for M-of-N multisig. \
                This single-service path will be removed in a future release.")]
    pub fn set_service(env: Env, new_service: Address) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        storage::get_admin(&env).require_auth();
        storage::set_service(&env, &new_service);
        events::service_updated(&env, &new_service);
        Ok(())
    }

    // ── Admin management ─────────────────────────────────────────────────────

    /// Initiate a two-step admin transfer.  The current admin calls this to
    /// nominate `new_admin`; `new_admin` must then call `accept_admin` to
    /// complete the handoff.  This prevents accidental loss of admin access.
    /// get_pending_admin() returns the nominate new_admin.
    pub fn transfer_admin(env: Env, new_admin: Address) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();
        storage::set_pending_admin(&env, &new_admin);
        events::admin_transfer_initiated(&env, &admin, &new_admin);
        Ok(())
    }

    /// Complete a pending admin transfer.  Must be called by the address
    /// nominated in `transfer_admin`.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let new_admin = Address::generate(&env);
    /// client.transfer_admin(&new_admin);
    /// client.accept_admin();
    /// assert_eq!(client.get_admin(), new_admin);
    /// ```
    pub fn accept_admin(env: Env) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        let pending = storage::get_pending_admin(&env).ok_or(Error::NoPendingAdminTransfer)?;
        pending.require_auth();
        storage::set_admin(&env, &pending);
        storage::clear_pending_admin(&env);
        events::admin_transfer_accepted(&env, &pending);
        Ok(())
    }

    /// Cancel a pending admin transfer.  Admin only.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let new_admin = Address::generate(&env);
    /// client.transfer_admin(&new_admin);
    /// client.cancel_admin_transfer();
    /// assert_eq!(client.get_admin(), admin);
    /// ```
    pub fn cancel_admin_transfer(env: Env) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        if !storage::has_pending_admin(&env) {
            return Err(Error::NoPendingAdminTransfer);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();
        storage::clear_pending_admin(&env);
        events::admin_transfer_cancelled(&env, &admin);
        Ok(())
    }

    // ── Pause circuit breaker ────────────────────────────────────────────────

    /// Pause the contract, blocking all score submissions.  Admin only.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// assert!(!client.is_paused());
    /// client.pause();
    /// assert!(client.is_paused());
    /// ```
    pub fn pause(env: Env) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();
        storage::set_paused(&env, true);
        events::contract_paused(&env, &admin);
        Ok(())
    }

    /// Resume normal operations after a pause.  Admin only.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// client.pause();
    /// assert!(client.is_paused());
    /// client.unpause();
    /// assert!(!client.is_paused());
    /// ```
    pub fn unpause(env: Env) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();
        storage::set_paused(&env, false);
        events::contract_unpaused(&env, &admin);
        Ok(())
    }

    /// Returns `true` when the contract is paused.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// assert!(!client.is_paused());
    /// ```
    pub fn is_paused(env: Env) -> bool {
        storage::is_paused(&env)
    }

    // ── Time-locked upgrade governance ────────────────────────────────────────

    /// Propose a contract WASM upgrade, starting the mandatory time-lock.
    ///
    /// The admin commits to `new_wasm_hash` (the hash of an already-installed
    /// WASM, as produced by `install_contract_wasm`). The proposal is recorded
    /// with `executable_after = now + get_upgrade_delay()`, and an
    /// `upgrade_proposed` event is emitted so monitoring services and the
    /// community can inspect and react during the delay window.
    ///
    /// Only the current admin may call this; a compromised *service* key
    /// cannot initiate an upgrade. The proposal does **not** take effect until
    /// `execute_upgrade` is called after the lock elapses, and it can be
    /// cancelled at any time before then via `veto_upgrade`.
    ///
    /// # Errors
    /// - [`Error::NotInitialized`] if the contract has no admin yet.
    /// - [`Error::UpgradeAlreadyPending`] if a proposal already exists — veto
    ///   or execute it first (one in-flight proposal at a time).
    pub fn propose_upgrade(env: Env, new_wasm_hash: BytesN<32>) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();

        if storage::has_pending_upgrade(&env) {
            return Err(Error::UpgradeAlreadyPending);
        }

        let now = env.ledger().timestamp();
        let delay = storage::get_upgrade_delay(&env);
        // delay is bounded to MAX_UPGRADE_DELAY_SECS on the way in, so this
        // addition cannot realistically overflow; saturate as defence in depth.
        let executable_after = now.saturating_add(delay);

        let proposal = UpgradeProposal {
            new_wasm_hash: new_wasm_hash.clone(),
            proposed_at: now,
            executable_after,
            proposed_by: admin,
        };
        storage::set_pending_upgrade(&env, &proposal);

        events::upgrade_proposed(&env, &new_wasm_hash, executable_after);
        Ok(())
    }

    /// Execute the pending upgrade once its time-lock has elapsed.
    ///
    /// Re-verifies — at execution time, never from a cached decision — that
    /// `now >= executable_after`, then invokes the Soroban upgrade primitive
    /// `env.deployer().update_current_contract_wasm(new_wasm_hash)` to swap in
    /// the new logic. The pending proposal is cleared and an `upgrade_executed`
    /// event is emitted.
    ///
    /// Admin only.
    ///
    /// # Errors
    /// - [`Error::NotInitialized`] if the contract has no admin yet.
    /// - [`Error::NoPendingUpgrade`] if there is no proposal to execute.
    /// - [`Error::UpgradeNotReady`] if the time-lock has not yet elapsed.
    pub fn execute_upgrade(env: Env) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();

        let proposal = storage::get_pending_upgrade(&env).ok_or(Error::NoPendingUpgrade)?;

        // Deterministic, caller-independent: the ledger timestamp cannot be
        // manipulated by the invoker. Re-checked here so a delay change or a
        // long-pending proposal is always evaluated against the real clock.
        let now = env.ledger().timestamp();
        if now < proposal.executable_after {
            return Err(Error::UpgradeNotReady);
        }

        // The actual Soroban upgrade primitive — replaces this contract's WASM.
        env.deployer().update_current_contract_wasm(proposal.new_wasm_hash.clone());

        storage::clear_pending_upgrade(&env);
        events::upgrade_executed(&env, &proposal.new_wasm_hash);
        Ok(())
    }

    /// Cancel the pending upgrade during the time-lock window.
    ///
    /// Intended as the emergency escape hatch if a proposal is malicious or the
    /// admin key was compromised and the legitimate admin (or a recovered key)
    /// wants to stop it before execution. Clears the proposal and emits an
    /// `upgrade_vetoed` event naming the caller for the audit trail.
    ///
    /// Admin only.
    ///
    /// # Errors
    /// - [`Error::NotInitialized`] if the contract has no admin yet.
    /// - [`Error::NoPendingUpgrade`] if there is no proposal to veto.
    pub fn veto_upgrade(env: Env) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();

        if !storage::has_pending_upgrade(&env) {
            return Err(Error::NoPendingUpgrade);
        }
        storage::clear_pending_upgrade(&env);

        events::upgrade_vetoed(&env, &admin);
        Ok(())
    }

    /// Returns the pending upgrade proposal so anyone can audit it during the
    /// time-lock window. Read-only and callable by any account or contract.
    ///
    /// # Errors
    /// - [`Error::NoPendingUpgrade`] if no proposal is currently pending.
    pub fn get_pending_upgrade(env: Env) -> Result<UpgradeProposal, Error> {
        storage::get_pending_upgrade(&env).ok_or(Error::NoPendingUpgrade)
    }

    /// Configure the upgrade time-lock delay (seconds) applied to future
    /// proposals. Must be within `[MIN_UPGRADE_DELAY_SECS,
    /// MAX_UPGRADE_DELAY_SECS]` (48 hours – 14 days). Admin only.
    ///
    /// Changing the delay only affects proposals created *after* the change;
    /// an already-pending proposal keeps its original `executable_after`.
    ///
    /// Security note: *raising* the delay is always safe. *Lowering* it
    /// shortens the community veto window and should only be done with broad
    /// community consensus — see the README's Upgrade Governance section.
    ///
    /// # Errors
    /// - [`Error::NotInitialized`] if the contract has no admin yet.
    /// - [`Error::InvalidUpgradeDelay`] if `delay_secs` is outside the bounds.
    pub fn set_upgrade_delay(env: Env, delay_secs: u64) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        if !(constants::MIN_UPGRADE_DELAY_SECS..=constants::MAX_UPGRADE_DELAY_SECS)
            .contains(&delay_secs)
        {
            return Err(Error::InvalidUpgradeDelay);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();
        storage::set_upgrade_delay(&env, delay_secs);
        Ok(())
    }

    /// Returns the current upgrade time-lock delay in seconds. Defaults to
    /// `DEFAULT_UPGRADE_DELAY_SECS` (48 hours) until configured.
    pub fn get_upgrade_delay(env: Env) -> u64 {
        storage::get_upgrade_delay(&env)
    }

    // ── Watchlist ────────────────────────────────────────────────────────────

    /// Add or remove `wallet` from the priority-monitoring watchlist.
    /// Watchlisted wallets receive elevated scrutiny in off-chain analysis.
    /// Admin only.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let wallet = Address::generate(&env);
    /// assert!(!client.is_watchlisted(&wallet));
    /// client.set_watchlist(&wallet, &true);
    /// assert!(client.is_watchlisted(&wallet));
    /// ```
    pub fn set_watchlist(env: Env, wallet: Address, flagged: bool) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        storage::get_admin(&env).require_auth();
        storage::set_watchlist(&env, &wallet, flagged);
        events::watchlist_updated(&env, &wallet, flagged);
        Ok(())
    }

    /// Returns `true` if `wallet` is on the priority-monitoring watchlist.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// let wallet = Address::generate(&env);
    /// assert!(!client.is_watchlisted(&wallet));
    /// ```
    pub fn is_watchlisted(env: Env, wallet: Address) -> bool {
        storage::is_watchlisted(&env, &wallet)
    }

    // ── Risk threshold ───────────────────────────────────────────────────────

    /// Set the global risk threshold (0-100).  Scores at or above this
    /// value will emit a `threshold_breached` event on every submission.
    /// Admin only.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// client.set_risk_threshold(&80);
    /// assert_eq!(client.get_risk_threshold(), 80);
    /// ```
    pub fn set_risk_threshold(env: Env, threshold: u32) -> Result<(), Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        if threshold > 100 {
            return Err(Error::InvalidScore);
        }
        let admin = storage::get_admin(&env);
        admin.require_auth();
        let old = storage::get_risk_threshold(&env);
        storage::set_risk_threshold(&env, threshold);
        events::threshold_updated(&env, old, threshold);
        Ok(())
    }

    /// Returns the current risk threshold.  Defaults to 75 until configured.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// assert_eq!(client.get_risk_threshold(), 75);
    /// ```
    pub fn get_risk_threshold(env: Env) -> u32 {
        storage::get_risk_threshold(&env)
    }

    // ── Read-only admin / service ─────────────────────────────────────────────

    /// Returns the current admin address.
    ///
    /// # Examples
    ///
    /// ```
    /// # use ledgerlens_score::LedgerLensScoreContractClient;
    /// # use soroban_sdk::{testutils::Address as _, Env, Address};
    /// # use ledgerlens_score::LedgerLensScoreContract;
    /// let env = Env::default();
    /// env.mock_all_auths();
    /// let contract_id = env.register_contract(None, LedgerLensScoreContract);
    /// let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    /// let admin = Address::generate(&env);
    /// let service = Address::generate(&env);
    /// client.initialize(&admin, &service);
    /// assert_eq!(client.get_admin(), admin);
    /// ```
    pub fn get_admin(env: Env) -> Result<Address, Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        Ok(storage::get_admin(&env))
    }

    /// Returns the current authorised scoring service address.
    ///
    /// # Deprecation notice
    ///
    /// This function is deprecated alongside [`set_service`].  Use
    /// [`get_service_signers`] and [`get_service_threshold`] for the M-of-N
    /// multisig model.
    #[deprecated(
        note = "Use get_service_signers / get_service_threshold for the M-of-N multisig model."
    )]
    pub fn get_service(env: Env) -> Result<Address, Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        Ok(storage::get_service(&env))
    }

    /// Returns the address nominated as the pending new admin, or
    /// `NoPendingAdminTransfer` if no transfer is in progress.
    pub fn get_pending_admin(env: Env) -> Result<Address, Error> {
        if !storage::has_admin(&env) {
            return Err(Error::NotInitialized);
        }
        storage::get_pending_admin(&env).ok_or(Error::NoPendingAdminTransfer)
    }

    /// Returns `true` if an admin transfer has been initiated but not yet
    /// accepted or cancelled.
    pub fn has_pending_admin_transfer(env: Env) -> bool {
        storage::has_pending_admin(&env)
    }

    // ── Internal helpers ──────────────────────────────────────────────────────

    /// Shared implementation behind `get_aggregate_score`. Iterates the
    /// wallet's registered pairs once, accumulating the weighted sum and
    /// weight total with checked arithmetic so a pathological admin-set
    /// weight can never panic the contract.
    fn compute_aggregate_score(env: &Env, wallet: &Address) -> Result<AggregateRiskScore, Error> {
        let pairs = storage::get_wallet_pairs(env, wallet);
        if pairs.is_empty() {
            return Err(Error::ScoreNotFound);
        }
        // Documents the O(N) bound this function is designed around; a
        // no-op in release builds (`debug-assertions = false`).
        debug_assert!(pairs.len() <= constants::MAX_WALLET_PAIRS);

        let mut weighted_sum: u64 = 0;
        let mut weight_sum: u64 = 0;
        let mut max_pair_score: u32 = 0;
        let mut max_pair: Symbol = pairs.get(0).unwrap();
        let mut benford_flag_count: u32 = 0;
        let mut ml_flag_count: u32 = 0;
        let mut last_updated: u64 = 0;

        for i in 0..pairs.len() {
            let pair = pairs.get(i).unwrap();
            let component = storage::get_score(env, wallet, &pair).ok_or(Error::ScoreNotFound)?;

            if i == 0 || component.score > max_pair_score {
                max_pair_score = component.score;
                max_pair = pair.clone();
            }
            if component.benford_flag {
                benford_flag_count += 1;
            }
            if component.ml_flag {
                ml_flag_count += 1;
            }
            if component.timestamp > last_updated {
                last_updated = component.timestamp;
            }

            let weight = storage::get_pair_weight(env, &pair);
            let product = weight.checked_mul(component.score).ok_or(Error::ArithmeticOverflow)?;
            weighted_sum =
                weighted_sum.checked_add(product as u64).ok_or(Error::ArithmeticOverflow)?;
            weight_sum = weight_sum.checked_add(weight as u64).ok_or(Error::ArithmeticOverflow)?;
        }

        // All contributing pairs have weight 0 — the average is undefined.
        if weight_sum == 0 {
            return Err(Error::ScoreNotFound);
        }

        // Bounded by construction: a weighted average of values in 0-100
        // can never itself exceed 100, so the downcast to u32 is safe.
        let aggregate_score = (weighted_sum / weight_sum) as u32;

        Ok(AggregateRiskScore {
            aggregate_score,
            pair_count: pairs.len(),
            max_pair_score,
            max_pair,
            benford_flag_count,
            ml_flag_count,
            last_updated,
        })
    }

    /// Best-effort refresh of the `AggregateScore(wallet)` cache after a
    /// score write. Failures are swallowed (e.g. a wallet whose only pair
    /// currently has weight 0) — the cache is informational only and must
    /// never cause `submit_score` / `submit_scores_batch` to fail.
    fn refresh_aggregate_cache(env: &Env, wallet: &Address) {
        if let Ok(aggregate) = Self::compute_aggregate_score(env, wallet) {
            storage::set_aggregate_score(env, wallet, &aggregate);
        }
    }
}
