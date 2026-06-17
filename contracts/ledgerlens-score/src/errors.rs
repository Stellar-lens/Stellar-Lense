use soroban_sdk::contracterror;

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    AlreadyInitialized = 1,
    NotInitialized = 2,
    Unauthorized = 3,
    InvalidScore = 4,
    InvalidConfidence = 5,
    ScoreNotFound = 6,
    /// Returned when any state-mutating call is attempted while the
    /// contract is paused by the admin.
    ContractPaused = 7,
    /// Returned when `accept_admin` or `cancel_admin_transfer` is called
    /// but no transfer has been initiated.
    NoPendingAdminTransfer = 8,
    /// Returned when `submit_scores_batch` is called with zero entries.
    EmptyBatch = 9,
    /// Returned when a batch exceeds the MAX_BATCH_SIZE limit.
    BatchTooLarge = 10,
    /// Returned when the weighted aggregate computation in
    /// `get_aggregate_score` would overflow.
    ArithmeticOverflow = 11,

    // ── Time-locked upgrade governance ────────────────────────────────────
    /// Returned when `execute_upgrade`, `veto_upgrade`, or
    /// `get_pending_upgrade` is called but no proposal exists.
    NoPendingUpgrade = 20,
    /// Returned when `execute_upgrade` is called before the time lock
    /// (`executable_after`) has elapsed.
    UpgradeNotReady = 21,
    /// Returned when `propose_upgrade` is called while a proposal is already
    /// pending. Veto or execute the existing one first.
    UpgradeAlreadyPending = 22,
    /// Returned when `set_upgrade_delay` is given a value below
    /// `MIN_UPGRADE_DELAY_SECS` or above `MAX_UPGRADE_DELAY_SECS`.
    InvalidUpgradeDelay = 23,
}
