.PHONY: install lint format test run scale-workers mutation-test
.PHONY: install lint format test run typecheck mutation-test
.PHONY: check-integrity dead-path-report env-docs env-docs-check

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

# ---------------------------------------------------------------------------
# Source package integrity checks (Issue #540)
#
# Filesystem + AST sweep for missing __init__.py, unresolved merge conflict
# markers, syntax errors, and empty modules. Runs automatically before every
# `pytest` session (see tests/conftest.py::pytest_sessionstart) — this
# target is for running it standalone, independent of the test suite.
# ---------------------------------------------------------------------------
check-integrity:
	$(PYTHON) scripts/check_package_integrity.py

# ---------------------------------------------------------------------------
# Dead-path detection for retired modules (Issue #547)
#
# Reports source modules with no inbound Python import and no reference in
# Makefile/CI/docs — candidates for removal. Read-only, never deletes code.
# ---------------------------------------------------------------------------
dead-path-report:
	$(PYTHON) scripts/detect_dead_paths.py

# ---------------------------------------------------------------------------
# Environment contract docs generated from config schemas (Issue #544)
#
# `env-docs` regenerates docs/environment_contract.md from config.py.
# `env-docs-check` fails (without writing) if the committed doc has drifted
# from config.py — wire this into CI to keep the contract doc honest.
# ---------------------------------------------------------------------------
env-docs:
	$(PYTHON) scripts/generate_env_contract_docs.py

env-docs-check:
	$(PYTHON) scripts/generate_env_contract_docs.py --check

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
