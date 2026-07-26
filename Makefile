.PHONY: install lint format test run scale-workers mutation-test
.PHONY: install lint format test run typecheck mutation-test
.PHONY: check-cycles probe-deps validate-readme validate-notebooks validate-all

VENV_BIN := $(abspath .venv/bin)
ifeq ($(wildcard $(VENV_BIN)/python),)
  PYTHON := python3
  PIP := pip3
  RUFF := ruff
  BLACK := black
  PYTEST := pytest
else
  PYTHON := $(VENV_BIN)/python
  PIP := $(VENV_BIN)/pip
  RUFF := $(VENV_BIN)/ruff
  BLACK := $(VENV_BIN)/black
  PYTEST := $(VENV_BIN)/pytest
endif

install:
	$(PIP) install -r requirements.txt
	$(PIP) install ruff black

lint:
	$(RUFF) check .
	$(BLACK) --check .

format:
	$(RUFF) check --fix .
	$(BLACK) .

test:
	$(PYTEST) -q

fuzz:
	@echo "Running fuzz tests for 60 seconds each..."
	timeout 65 python tests/fuzz/fuzz_avro_codec.py tests/fuzz/corpus/ -max_len=10000 -timeout=10 || true
	timeout 65 python tests/fuzz/fuzz_horizon_response.py tests/fuzz/corpus/ -max_len=50000 -timeout=10 || true
	@echo "Fuzz testing complete."

test-e2e:
	@echo "Running end-to-end integration tests (requires LEDGERLENS_INTEGRATION_TESTS=1)..."
	LEDGERLENS_INTEGRATION_TESTS=1 $(PYTEST) tests/integration/test_full_pipeline_e2e.py -v --timeout=120

run:
	python run_pipeline.py

scale-workers:
	@if [ -z "$(N)" ]; then \
		echo "Error: N is required. Usage: make scale-workers N=4"; \
		exit 1; \
	fi
	python -m scripts.kafka_workers --num-workers $(N)
	$(PYTHON) run_pipeline.py

# ---------------------------------------------------------------------------
# Mutation testing — enforces ≥80% mutation score on the core scoring path
#
# Usage:
#   make mutation-test              # run and enforce threshold
#   make mutation-test THRESHOLD=70 # override threshold (for debugging)
#
# Runtime target: < 15 minutes in CI (--paths-to-mutate limits scope).
# Mutated files are never written to disk; mutmut restores originals after
# each probe, so no mutated code is persisted.
# ---------------------------------------------------------------------------
MUTATION_THRESHOLD ?= 80
MUTATION_PATHS = detection/benford_engine.py,detection/feature_engineering.py,detection/model_inference.py

mutation-test:
	@echo "==> Running mutation tests on core scoring path..."
	@echo "    Targets: $(MUTATION_PATHS)"
	@echo "    Threshold: $(MUTATION_THRESHOLD)%"
	mutmut run \
		--paths-to-mutate "$(MUTATION_PATHS)" \
		--runner "python -m pytest -x -q --timeout=30 -m 'not integration and not slow' \
			tests/test_benford.py \
			tests/test_benford_ci.py \
			tests/test_feature_engineering.py \
			tests/test_model_inference.py" \
		--no-progress || true
	@echo "==> Mutation results:"
	mutmut results || true
	$(PYTHON) scripts/check_mutation_score.py --threshold $(MUTATION_THRESHOLD)

# ---------------------------------------------------------------------------
# Import cycle detection (Issue #546)
#
# Usage:
#   make check-cycles                  # check all packages
#   make check-cycles PACKAGES="detection ingestion"  # specific packages
#
# Exit codes: 0 = clean, 2 = cycles found.
# ---------------------------------------------------------------------------
CYCLE_PACKAGES ?=

check-cycles:
	@echo "==> Checking for import cycles..."
	@if [ -n "$(CYCLE_PACKAGES)" ]; then \
		$(PYTHON) scripts/check_import_cycles.py --packages $(CYCLE_PACKAGES); \
	else \
		$(PYTHON) scripts/check_import_cycles.py; \
	fi

# ---------------------------------------------------------------------------
# Optional dependency probes (Issue #542)
#
# Usage:
#   make probe-deps                   # probe all groups
#   make probe-deps PROBE_GROUPS="gnn kafka"   # probe specific groups
#   make probe-deps-json              # JSON output
#
# Exit codes: 0 = all available, 2 = some missing.
# ---------------------------------------------------------------------------
PROBE_GROUPS ?=

probe-deps:
	@echo "==> Probing optional dependencies..."
	@if [ -n "$(PROBE_GROUPS)" ]; then \
		$(PYTHON) -m utils.dependency_probe --groups $(PROBE_GROUPS); \
	else \
		$(PYTHON) -m utils.dependency_probe; \
	fi

probe-deps-json:
	$(PYTHON) -m utils.dependency_probe --json

# ---------------------------------------------------------------------------
# README examples validation (Issue #548)
#
# Usage:
#   make validate-readme              # validate README.md only
#   make validate-readme DOCS="README.md docs/"  # include docs/ directory
#   make validate-readme-warn         # warn-only mode (never fails CI)
#
# Exit codes: 0 = all valid, 2 = broken references found.
# ---------------------------------------------------------------------------
DOCS ?= README.md

validate-readme:
	@echo "==> Validating README bash examples..."
	$(PYTHON) scripts/validate_readme_examples.py --docs $(DOCS)

validate-readme-warn:
	$(PYTHON) scripts/validate_readme_examples.py --docs $(DOCS) --warn-only

# ---------------------------------------------------------------------------
# Notebook validation (Issue #549)
#
# Usage:
#   make validate-notebooks           # structure checks (default)
#   make validate-notebooks-strict    # structure + outputs + strict markers
#   make validate-notebooks-ci        # full CI gate (outputs + exec counts + strict)
#
# Exit codes: 0 = pass, 2 = failures found.
# ---------------------------------------------------------------------------

validate-notebooks:
	@echo "==> Validating notebooks (structure)..."
	$(PYTHON) scripts/validate_notebooks.py

validate-notebooks-strict:
	$(PYTHON) scripts/validate_notebooks.py --strict

validate-notebooks-ci:
	@echo "==> Validating notebooks (CI gate: outputs + execution count + strict)..."
	$(PYTHON) scripts/validate_notebooks.py --check-outputs --check-execution-count --strict

# ---------------------------------------------------------------------------
# validate-all — run all 4 validation tools in sequence
#
# Usage:  make validate-all
# ---------------------------------------------------------------------------

validate-all: check-cycles probe-deps validate-readme validate-notebooks
	@echo "==> All validation checks complete."
