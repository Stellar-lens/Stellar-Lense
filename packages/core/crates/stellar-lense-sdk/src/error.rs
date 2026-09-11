use std::fmt;

/// Errors that can occur when using the StellarLense client.
///
/// # Examples
///
/// ```no_run
/// use stellar_lense_sdk::{StellarLenseClient, StellarLenseError};
///
/// #[tokio::main]
/// async fn main() {
///     let client = StellarLenseClient::new("https://api.stellar-lense.io", None);
///     match client.get_score("GABCDEF").await {
///         Ok(response) => println!("Got {} scores", response.scores.len()),
///         Err(StellarLenseError::NotFound(_)) => eprintln!("Wallet not found"),
///         Err(StellarLenseError::Unauthorized(_)) => eprintln!("Invalid API key"),
///         Err(StellarLenseError::RateLimited(_)) => eprintln!("Rate limit exceeded; back off"),
///         Err(StellarLenseError::HttpError(msg)) => eprintln!("Network error: {}", msg),
///         Err(e) => eprintln!("Other error: {}", e),
///     }
/// }
/// ```
#[derive(Debug, Clone)]
pub enum StellarLenseError {
    /// HTTP request failed (network error, DNS resolution failure, etc.)
    HttpError(String),
    /// The API returned an error response.
    Api { status_code: u16, message: String },
    /// The request was unauthorized (401).
    Unauthorized(String),
    /// The requested resource was not found (404).
    NotFound(String),
    /// Rate limit exceeded (429).
    RateLimited(String),
    /// JSON deserialization failed.
    Deserialization(String),
    /// URL parsing failed.
    InvalidUrl(String),
    /// TLS certificate validation failed; use `danger_accept_invalid_certs(true)`
    /// only for local testing.
    TlsError(String),
}

impl std::error::Error for StellarLenseError {}

impl fmt::Display for StellarLenseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StellarLenseError::HttpError(msg) => write!(f, "HTTP error: {}", msg),
            StellarLenseError::Api {
                status_code,
                message,
            } => {
                write!(f, "API error ({}): {}", status_code, message)
            }
            StellarLenseError::Unauthorized(msg) => write!(f, "Unauthorized (401): {}", msg),
            StellarLenseError::NotFound(msg) => write!(f, "Not found (404): {}", msg),
            StellarLenseError::RateLimited(msg) => write!(f, "Rate limited (429): {}", msg),
            StellarLenseError::Deserialization(msg) => write!(f, "Deserialization error: {}", msg),
            StellarLenseError::InvalidUrl(msg) => write!(f, "Invalid URL: {}", msg),
            StellarLenseError::TlsError(msg) => write!(f, "TLS error: {}", msg),
        }
    }
}

impl From<reqwest::Error> for StellarLenseError {
    fn from(e: reqwest::Error) -> Self {
        if e.is_status() {
            let status = e.status().unwrap_or_default();
            let msg = e.to_string();
            match status.as_u16() {
                401 => StellarLenseError::Unauthorized(msg),
                404 => StellarLenseError::NotFound(msg),
                429 => StellarLenseError::RateLimited(msg),
                _ => StellarLenseError::Api {
                    status_code: status.as_u16(),
                    message: msg,
                },
            }
        } else if e.is_connect() || e.is_timeout() {
            StellarLenseError::HttpError(e.to_string())
        } else if e.is_builder() {
            StellarLenseError::InvalidUrl(e.to_string())
        } else {
            StellarLenseError::HttpError(e.to_string())
        }
    }
}

impl From<serde_json::Error> for StellarLenseError {
    fn from(e: serde_json::Error) -> Self {
        StellarLenseError::Deserialization(e.to_string())
    }
}

/// Errors from ZK proof verification (only available with `zk-verify` feature).
#[cfg(feature = "zk-verify")]
#[derive(Debug, Clone)]
pub enum ZkVerifyError {
    /// The proof has an invalid wire format or field count.
    InvalidFormat(String),
    /// A curve arithmetic operation failed (point not on curve, etc.).
    CurveError(String),
    /// The Fiat-Shamir challenge mismatched.
    ChallengeMismatch,
    /// A bit commitment verification failed.
    BitProofFailed(usize),
    /// The aggregate sum of bit commitments does not match the expected value.
    AggregateMismatch,
    /// The threshold exceeds MAX_SCORE (100).
    InvalidThreshold(u32),
}

#[cfg(feature = "zk-verify")]
impl std::error::Error for ZkVerifyError {}

#[cfg(feature = "zk-verify")]
impl fmt::Display for ZkVerifyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ZkVerifyError::InvalidFormat(msg) => write!(f, "Invalid proof format: {}", msg),
            ZkVerifyError::CurveError(msg) => write!(f, "Curve arithmetic error: {}", msg),
            ZkVerifyError::ChallengeMismatch => write!(f, "Fiat-Shamir challenge mismatch"),
            ZkVerifyError::BitProofFailed(i) => write!(f, "Bit proof {} failed verification", i),
            ZkVerifyError::AggregateMismatch => {
                write!(f, "Aggregate sum of bit commitments does not match")
            }
            ZkVerifyError::InvalidThreshold(t) => {
                write!(f, "Invalid threshold {} (must be <= 100)", t)
            }
        }
    }
}
