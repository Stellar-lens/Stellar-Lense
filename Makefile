.PHONY: install lint format test run scale-workers mutation-test threshold-sweep anonymization-check
.PHONY: install lint format test run typecheck mutation-test threshold-sweep anonymization-check

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
# Threshold sweep — run threshold diagnostics on a backtest dataset
#
# Usage:
#   make threshold-sweep DATASET=data/backtest.parquet
#   make threshold-sweep DATASET=data/backtest.parquet OUTPUT=reports/
# ---------------------------------------------------------------------------
DATASET ?= data/backtest.parquet
SWEEP_OUTPUT ?= reports/

threshold-sweep:
	@echo "==> Running threshold sweep diagnostics..."
	@echo "    Dataset: $(DATASET)"
	@echo "    Output:  $(SWEEP_OUTPUT)"
	$(PYTHON) -m evaluation.backtest $(DATASET) $(SWEEP_OUTPUT) --sweep
	@echo "==> Threshold sweep complete. Report in $(SWEEP_OUTPUT)/backtest_report.json"

# ---------------------------------------------------------------------------
# Anonymization check — ensure shared example data is free of PII
#
# Usage:
#   make anonymization-check
# ---------------------------------------------------------------------------
anonymization-check:
	@echo "==> Running anonymization checks..."
	$(PYTHON) scripts/check_anonymization.py --target data tests/fixtures tests/fuzz/corpus
	@echo "==> Anonymization check complete."
