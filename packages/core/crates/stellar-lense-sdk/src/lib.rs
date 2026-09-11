//! # StellarLense SDK (Rust)
//!
//! A typed Rust client for the StellarLense REST API, with optional zero-knowledge
//! proof verification for threshold proofs.
//!
//! ## Quick Start
//!
//! ```no_run
//! use stellar_lense_sdk::StellarLenseClient;
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let client = StellarLenseClient::new(
//!         "https://api.stellar-lense.io",
//!         Some("sk_your_api_key".into()),
//!     );
//!
//!     // Fetch scores for a specific wallet
//!     let scores = client.get_score("GA…").await?;
//!     println!("{:?}", scores);
//!
//!     // Check health
//!     let health = client.health().await?;
//!     println!("API status: {}", health.status);
//!
//!     Ok(())
//! }
//! ```
//!
//! ## Feature Flags
//!
//! - `async` (default): Enable async/await support via `tokio`.
//! - `zk-verify`: Enable ZK threshold proof verification using ark-bn254.

pub mod client;
pub mod error;
pub mod models;

#[cfg(feature = "zk-verify")]
pub mod zk;

// Re-exports for convenience.
pub use client::StellarLenseClient;
pub use error::StellarLenseError;
pub use models::{CrossChainLink, HealthStatus, Ring, RiskScore, WalletScoresResponse};

#[cfg(feature = "zk-verify")]
pub use zk::verify_threshold_proof;

#[cfg(feature = "zk-verify")]
pub use error::ZkVerifyError;

#[cfg(feature = "zk-verify")]
pub use models::{BitProof, ThresholdProof};
