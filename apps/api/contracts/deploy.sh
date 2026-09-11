#!/usr/bin/env bash
# Build and deploy the StellarLense score contract to Stellar Testnet.
#
# Requires: soroban-cli, a funded testnet identity configured as
# `stellar-lense-admin` (`soroban keys generate stellar-lense-admin --network testnet`).
set -euo pipefail

CONTRACT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/stellar-lense-score" && pwd)"
WASM_PATH="$CONTRACT_DIR/target/wasm32-unknown-unknown/release/stellar_lense_score.wasm"
NETWORK="${NETWORK:-testnet}"
SOURCE_ACCOUNT="${SOURCE_ACCOUNT:-stellar-lense-admin}"

echo "Building contract..."
cargo build --manifest-path "$CONTRACT_DIR/Cargo.toml" \
  --target wasm32-unknown-unknown --release

echo "Deploying to $NETWORK..."
CONTRACT_ID=$(soroban contract deploy \
  --wasm "$WASM_PATH" \
  --source "$SOURCE_ACCOUNT" \
  --network "$NETWORK")

echo "Contract deployed: $CONTRACT_ID"

echo "Initializing admin..."
soroban contract invoke \
  --id "$CONTRACT_ID" \
  --source "$SOURCE_ACCOUNT" \
  --network "$NETWORK" \
  -- initialize --admin "$SOURCE_ACCOUNT"

echo "Done. StellarLense score contract ID: $CONTRACT_ID"
