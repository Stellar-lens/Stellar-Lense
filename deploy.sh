#!/usr/bin/env bash
# Build, optimize, deploy and initialize the LedgerLens score contract.
#
# Usage: ./deploy.sh <network> <admin-identity> <service-address>
#   network         soroban CLI network name (e.g. testnet, futurenet)
#   admin-identity  soroban CLI identity used to deploy/initialize
#   service-address Stellar address authorised to call submit_score

set -euo pipefail

NETWORK="${1:-testnet}"
ADMIN_IDENTITY="${2:-deployer}"
SERVICE_ADDRESS="${3:?service-address argument is required}"

WASM_PATH="target/wasm32-unknown-unknown/release/ledgerlens_score.wasm"
OPTIMIZED_WASM_PATH="target/wasm32-unknown-unknown/release/ledgerlens_score.optimized.wasm"

echo "==> Building contract"
cargo build --target wasm32-unknown-unknown --release -p ledgerlens-score

echo "==> Optimizing wasm"
soroban contract optimize --wasm "$WASM_PATH"

echo "==> Deploying to $NETWORK"
CONTRACT_ID=$(soroban contract deploy \
  --wasm "$OPTIMIZED_WASM_PATH" \
  --source "$ADMIN_IDENTITY" \
  --network "$NETWORK")

echo "==> Deployed contract: $CONTRACT_ID"

ADMIN_ADDRESS=$(soroban keys address "$ADMIN_IDENTITY")

echo "==> Initializing contract"
soroban contract invoke \
  --id "$CONTRACT_ID" \
  --source "$ADMIN_IDENTITY" \
  --network "$NETWORK" \
  -- \
  initialize \
  --admin "$ADMIN_ADDRESS" \
  --service "$SERVICE_ADDRESS"

echo "==> Done. Contract ID: $CONTRACT_ID"
