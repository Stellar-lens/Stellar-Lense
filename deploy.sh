#!/usr/bin/env bash
# Build, optimize, deploy and initialize the LedgerLens score contract.
#
# Usage:
#   ./deploy.sh [options] <network> <admin-identity> <service-address>
#
# Options:
#   --dry-run   Print the commands that would be executed without running them.
#   --help      Show this help message.
#
# Arguments:
#   network           soroban CLI network alias (e.g. testnet, futurenet)
#   admin-identity    soroban CLI identity used to deploy and initialize
#   service-address   Stellar public key authorised to call submit_score

set -euo pipefail

DRY_RUN=false
POSITIONAL=()
CARGO_BIN="${CARGO_BIN:-cargo}"
SOROBAN_BIN="${SOROBAN_BIN:-soroban}"

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --help)
      sed -n '3,20p' "$0"
      exit 0
      ;;
    *) POSITIONAL+=("$arg") ;;
  esac
done
set -- "${POSITIONAL[@]+"${POSITIONAL[@]}"}"

NETWORK="${1:-testnet}"
ADMIN_IDENTITY="${2:-deployer}"
SERVICE_ADDRESS="${3:?ERROR: service-address argument is required}"

WASM_PATH="target/wasm32-unknown-unknown/release/ledgerlens_score.wasm"
OPTIMIZED_WASM_PATH="target/wasm32-unknown-unknown/release/ledgerlens_score.optimized.wasm"

# ── Helpers ───────────────────────────────────────────────────────────────────

run() {
  if [ "$DRY_RUN" = true ]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

log() { echo "==> $*"; }

die() {
  echo "ERROR: $*" >&2
  exit 1
}

diagnose_rpc_failure() {
  local operation="$1"
  local output="$2"

  echo "ERROR: ${operation} failed." >&2
  echo "$output" >&2

  case "$output" in
    *"timed out"*|*"timeout"*)
      echo "HINT: RPC confirmation timed out; the transaction may have been submitted, so deployment state is unconfirmed." >&2
      ;;
    *"tx_bad_seq"*|*"bad sequence"*|*"sequence"*)
      echo "HINT: Sequence number rejected. Refresh the source account state and retry once outstanding transactions settle." >&2
      ;;
    *"connection refused"*|*"dns error"*|*"http request failed"*|*"network error"*)
      echo "HINT: RPC endpoint appears unavailable. Check the selected network alias and Soroban RPC connectivity." >&2
      ;;
  esac
}

run_capture() {
  local operation="$1"
  shift

  if [ "$DRY_RUN" = true ]; then
    echo "[dry-run] $*"
    return 0
  fi

  local output
  if ! output=$("$@" 2>&1); then
    diagnose_rpc_failure "$operation" "$output"
    return 1
  fi

  printf '%s\n' "$output"
}

# ── Validate inputs ───────────────────────────────────────────────────────────

case "$NETWORK" in
  testnet|futurenet|mainnet) ;;
  *)
    echo "WARNING: '$NETWORK' is not a recognised Stellar network alias." >&2
    echo "         Proceeding anyway — ensure the alias is configured in soroban config." >&2
    ;;
esac

if [ "$NETWORK" = "mainnet" ]; then
  echo ""
  echo "  ╔══════════════════════════════════════════════════════╗"
  echo "  ║  MAINNET DEPLOYMENT — this action cannot be undone  ║"
  echo "  ╚══════════════════════════════════════════════════════╝"
  echo ""
  read -rp "  Type 'deploy-mainnet' to confirm: " CONFIRM
  [ "$CONFIRM" = "deploy-mainnet" ] || { echo "Aborted."; exit 1; }
fi

# ── Build ─────────────────────────────────────────────────────────────────────

log "Building contract (wasm32-unknown-unknown, release)"
run "$CARGO_BIN" build --target wasm32-unknown-unknown --release -p ledgerlens-score

log "Optimizing wasm"
run "$SOROBAN_BIN" contract optimize --wasm "$WASM_PATH"

# ── Deploy ────────────────────────────────────────────────────────────────────

log "Deploying to $NETWORK"
if [ "$DRY_RUN" = true ]; then
  CONTRACT_ID="<CONTRACT_ID_PLACEHOLDER>"
  echo "[dry-run] $SOROBAN_BIN contract deploy --wasm $OPTIMIZED_WASM_PATH --source $ADMIN_IDENTITY --network $NETWORK"
else
  CONTRACT_ID=$(run_capture "Contract deployment" "$SOROBAN_BIN" contract deploy \
    --wasm "$OPTIMIZED_WASM_PATH" \
    --source "$ADMIN_IDENTITY" \
    --network "$NETWORK") || die "Deployment did not complete."
fi

[ -n "$CONTRACT_ID" ] || die "Deployment returned an empty contract id."
log "Deployment transaction returned contract id: $CONTRACT_ID"

# ── Initialize ────────────────────────────────────────────────────────────────

if [ "$DRY_RUN" = true ]; then
  ADMIN_ADDRESS="<ADMIN_ADDRESS>"
else
  ADMIN_ADDRESS=$(run_capture "Admin identity lookup" "$SOROBAN_BIN" keys address "$ADMIN_IDENTITY") \
    || die "Could not resolve the admin identity address."
fi

log "Initializing contract (admin=$ADMIN_ADDRESS, service=$SERVICE_ADDRESS)"
if ! run_capture "Contract initialization" "$SOROBAN_BIN" contract invoke \
  --id "$CONTRACT_ID" \
  --source "$ADMIN_IDENTITY" \
  --network "$NETWORK" \
  -- \
  initialize \
  --admin "$ADMIN_ADDRESS" \
  --service "$SERVICE_ADDRESS" >/dev/null; then
  echo "Contract id: $CONTRACT_ID" >&2
  die "Initialization failed; do not treat this deployment as successful."
fi

# ── Verify ────────────────────────────────────────────────────────────────────

log "Verifying deployment"
if [ "$DRY_RUN" = false ]; then
  STORED_ADMIN=$(run_capture "Post-deployment verification (get_admin)" "$SOROBAN_BIN" contract invoke \
    --id "$CONTRACT_ID" \
    --source "$ADMIN_IDENTITY" \
    --network "$NETWORK" \
    -- \
    get_admin) || {
      echo "Contract id: $CONTRACT_ID" >&2
      die "Post-deployment verification failed."
    }

  log "Admin verified on-chain: $STORED_ADMIN"

  CONTRACT_VERSION=$(run_capture "Post-deployment version check" "$SOROBAN_BIN" contract invoke \
    --id "$CONTRACT_ID" \
    --source "$ADMIN_IDENTITY" \
    --network "$NETWORK" \
    -- \
    get_version) || {
      echo "Contract id: $CONTRACT_ID" >&2
      die "Deployment verification could not read the contract version."
    }

  log "Contract version: $CONTRACT_VERSION"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "  ── Deployment complete ──────────────────────────────────"
echo "  Network:    $NETWORK"
echo "  Contract:   $CONTRACT_ID"
echo "  Admin:      $ADMIN_ADDRESS"
echo "  Service:    $SERVICE_ADDRESS"
echo "  ─────────────────────────────────────────────────────────"
echo ""
echo "  Save CONTRACT_ID=$CONTRACT_ID in your environment and in"
echo "  the api repo's .env before routing submit_score calls."
echo ""
