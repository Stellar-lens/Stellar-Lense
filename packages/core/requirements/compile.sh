#!/usr/bin/env bash
# requirements/compile.sh
# ─────────────────────────────────────────────────────────────────────────────
# Regenerates ALL requirements/*.txt lockfiles from their *.in source files.
#
# Usage:
#   bash requirements/compile.sh          # regenerate everything
#   bash requirements/compile.sh base     # regenerate only base.txt
#
# Prerequisites:
#   pip install pip-tools
#
# The generated *.txt files are committed to the repository so that CI and
# container builds can install deterministic, hash-verified dependency trees
# without running the solver.  Run this script whenever you change a version
# constraint in pyproject.toml or any *.in file, then commit the updated *.txt.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
REQ_DIR="$SCRIPT_DIR"

# Which surfaces to compile (order matters — later ones reference earlier ones)
SURFACES=(base test dev docs fuzz ml chain)

# Filter to a subset if arguments are given
if [ "$#" -gt 0 ]; then
    SURFACES=("$@")
fi

# Ensure pip-tools is available
if ! command -v pip-compile &>/dev/null; then
    echo "ERROR: pip-compile not found. Install it with: pip install pip-tools" >&2
    exit 1
fi

echo "Compiling requirements lockfiles..."
echo ""

for surface in "${SURFACES[@]}"; do
    in_file="$REQ_DIR/${surface}.in"
    out_file="$REQ_DIR/${surface}.txt"

    if [ ! -f "$in_file" ]; then
        echo "WARNING: $in_file not found, skipping." >&2
        continue
    fi

    echo "  → requirements/${surface}.txt"
    pip-compile \
        --generate-hashes \
        --allow-unsafe \
        --strip-extras \
        --no-emit-index-url \
        --output-file "$out_file" \
        --resolver=backtracking \
        "$in_file"
done

echo ""
echo "Done. Commit the updated requirements/*.txt files."
