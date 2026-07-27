.PHONY: install lint format test run scale-workers mutation-test validate maturity
.PHONY: install lint format test run typecheck mutation-test

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
# Contributor validation suite — Issue #558
#
# Usage:
#   make validate              # run all suites
#   make validate SUITE=parsing
#   make validate SUITE=reconciliation REPORT=reports/validation.json
# ---------------------------------------------------------------------------
SUITE ?= all
VALIDATION_REPORT ?=

validate:
	@echo "==> Running LedgerLens contributor validation suite (suite: $(SUITE))..."
	$(PYTHON) -m scripts.validate \
		--suite $(SUITE) \
		$(if $(VALIDATION_REPORT),--report $(VALIDATION_REPORT),) \
		--verbose

# ---------------------------------------------------------------------------
# Repository maturity tracking — Issue #560
#
# Usage:
#   make maturity
#   make maturity MATURITY_REPORT=reports/maturity.json
#   make maturity MATURITY_THRESHOLD=70
# ---------------------------------------------------------------------------
MATURITY_REPORT ?=
MATURITY_THRESHOLD ?= 60

maturity:
	@echo "==> Running LedgerLens repository maturity check (threshold: $(MATURITY_THRESHOLD))..."
	$(PYTHON) -m scripts.repo_maturity \
		--threshold $(MATURITY_THRESHOLD) \
		$(if $(MATURITY_REPORT),--report $(MATURITY_REPORT),) \
		--verbose || true
