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
    /// Fewer than the configured threshold of signers were provided to
    /// `submit_score`.
    InsufficientSigners = 14,
    /// A signer passed to `submit_score` is not a member of the service set.
    UnauthorizedSigner = 15,
    /// `set_service_threshold` was called with `0` or a value exceeding
    /// the current service-set size.
    InvalidThreshold = 16,
    /// `add_service_signer` was called when the service set already contains
    /// `MAX_SERVICE_SIGNERS` members.
    ServiceSetFull = 17,
    /// `add_service_signer` was called with an address already in the set.
    SignerAlreadyInSet = 18,
    /// `remove_service_signer` was called with an address not in the set.
    SignerNotInSet = 19,
}
