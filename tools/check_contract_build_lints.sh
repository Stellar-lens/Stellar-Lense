#!/usr/bin/env bash

set -euo pipefail

PACKAGES=(
  ledgerlens-score
  ledgerlens-aggregator
)

echo "Checking contract-only builds for dead code with wasm-target lints enabled"

for package in "${PACKAGES[@]}"; do
  echo "==> ${package}"
  cargo rustc \
    --package "${package}" \
    --lib \
    --target wasm32-unknown-unknown \
    --release \
    --locked \
    -- \
    -Dwarnings
done

echo ""
echo "Contract-only lint check passed."
echo "Intentional native-only exceptions are documented in docs/contract-build-lints.md."
