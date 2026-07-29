.PHONY: install lint format test run scale-workers typecheck mutation-test threshold-sweep anonymization-check check-env check-schema-compatibility check-review-gates ops-check ops-validate static-analysis benchmark verify-lockfile regenerate-lockfile

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
# Review gates for high-risk data and model changes
#
#   make check-schema-compatibility   # Avro wire-schema compatibility
#   make check-review-gates           # high-risk path acknowledgement
#
# check-schema-compatibility is the exact command CI runs.
#
# check-review-gates reports what CI would decide but always exits 0, since
# locally there is usually no pull-request body yet. Unlike CI — which sees a
# pushed branch — it also counts uncommitted and untracked files, so it is
# useful before you commit. Reads the body from PR_BODY_FILE when supplied:
#
#   make check-review-gates PR_BODY_FILE=/tmp/body.md
#
# To reproduce a CI failure exactly, drop --dry-run:
#
#   python scripts/check_review_gates.py \
#       --changed-paths-from <file> --pr-body-file <file>
# ---------------------------------------------------------------------------
BASE ?= main
PR_BODY_FILE ?=

check-schema-compatibility:
	$(PYTHON) scripts/check_schema_compatibility.py

check-review-gates:
	@{ \
		git diff --name-only $(BASE)...HEAD; \
		git diff --name-only HEAD; \
		git ls-files --others --exclude-standard; \
	} | sort -u > .changed_paths.tmp
	@$(PYTHON) scripts/check_review_gates.py \
		--changed-paths-from .changed_paths.tmp \
		$(if $(PR_BODY_FILE),--pr-body-file $(PR_BODY_FILE),--pr-body "") \
		--dry-run
	@rm -f .changed_paths.tmp

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

# Validate environment configuration contracts (config/contracts.py) without
# starting the service. Usage:
#   make check-env MODE=api        # validate one runtime mode
#   make check-env                 # validate every known runtime mode
check-env:
	$(PYTHON) -m scripts.check_env $(if $(MODE),--mode $(MODE),--all)

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
# Static analysis gate — mypy + bandit + radon (issue #545)
# ---------------------------------------------------------------------------
static-analysis:
	@echo "==> Running repository-wide static analysis gate..."
	$(PYTHON) scripts/static_analysis_gate.py

# Run only mypy (fast, no subprocess)
typecheck:
	$(PYTHON) -m mypy detection ingestion streaming ci_metrics benchmarks utils config.py

# ---------------------------------------------------------------------------
# Benchmark datasets — run detector benchmarks (issue #537)
# ---------------------------------------------------------------------------
benchmark:
	@echo "==> Running detector benchmark suite..."
	$(PYTHON) -m benchmarks.datasets
	@echo "To run benchmarks against a detector, see benchmarks/runner.py"

# ---------------------------------------------------------------------------
# Lockfile verification (issue #541)
# ---------------------------------------------------------------------------
verify-lockfile:
	@echo "==> Verifying installed environment matches requirements.lock..."
	$(PYTHON) scripts/verify_lockfile.py

regenerate-lockfile:
	@echo "==> Regenerating requirements.lock from current environment..."
	$(PYTHON) scripts/verify_lockfile.py --generate

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

ops-check:
	python -m cli.main healthcheck

ops-validate:
	python -m cli.main validate-artifacts
