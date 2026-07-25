.PHONY: install lint format test run scale-workers mutation-test
.PHONY: install lint format test run typecheck mutation-test
.PHONY: partition-write partition-read retention-scan snapshot-freeze run-compare

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
# Issue #527 — Partitioned dataset helpers
#
# Usage:
#   make partition-write DATA=data/synthetic_dataset.parquet STRATEGY=time PERIOD=month
#   make partition-read  ROOT=data/partitioned
# ---------------------------------------------------------------------------
DATA ?= data/synthetic_dataset.parquet
STRATEGY ?= time
PERIOD ?= month
PARTITION_ROOT ?= data/partitioned

partition-write:
	@echo "==> Writing partitioned dataset from $(DATA) (strategy=$(STRATEGY), period=$(PERIOD))"
	$(PYTHON) - <<'EOF'
import pandas as pd
from pathlib import Path
from data.partitioning import PartitionedDatasetWriter, TimePartitionStrategy, PairPartitionStrategy, WalletPartitionStrategy

strat_name = "$(STRATEGY)"
if strat_name == "time":
    strategy = TimePartitionStrategy(period="$(PERIOD)")
elif strat_name == "pair":
    strategy = PairPartitionStrategy()
else:
    strategy = WalletPartitionStrategy()

df = pd.read_parquet("$(DATA)")
writer = PartitionedDatasetWriter(root=Path("$(PARTITION_ROOT)"), strategy=strategy)
result = writer.write(df)
print(f"Written {sum(result.values())} rows across {len(result)} partition(s).")
for k, n in sorted(result.items()):
    print(f"  {k}: {n} rows")
EOF

partition-read:
	@echo "==> Listing partitions under $(PARTITION_ROOT)"
	$(PYTHON) - <<'EOF'
from pathlib import Path
from data.partitioning import PartitionedDatasetReader
reader = PartitionedDatasetReader(Path("$(PARTITION_ROOT)"))
parts = reader.list_partitions()
print(f"Found {len(parts)} partition(s):")
for p in parts:
    meta = reader.get_metadata(p)
    rows = meta.row_count if meta else "?"
    print(f"  {p}: {rows} rows")
EOF

# ---------------------------------------------------------------------------
# Issue #530 — Data retention scan / purge
#
# Usage:
#   make retention-scan              # dry-run using default policies
#   make retention-scan DRY_RUN=0   # live purge
# ---------------------------------------------------------------------------
DRY_RUN ?= 1

retention-scan:
	@echo "==> Running retention scan (dry_run=$(DRY_RUN))"
	$(PYTHON) - <<'EOF'
from data.retention import FileRetentionManager, DEFAULT_POLICIES
from pathlib import Path
dry = "$(DRY_RUN)" != "0"
manager = FileRetentionManager(
    policies=DEFAULT_POLICIES,
    base_dir=Path("."),
    audit_log_path=Path("reports/retention_audit.ndjson"),
)
report = manager.run(dry_run=dry)
print(report.summary())
EOF

# ---------------------------------------------------------------------------
# Issue #533 — Dataset snapshot helpers
#
# Usage:
#   make snapshot-freeze SOURCE=data/synthetic_dataset.parquet LABEL=pre-training
#   make snapshot-list
#   make snapshot-verify SNAPSHOT_ID=snap_20240601T000000_pre-training_abc12345
# ---------------------------------------------------------------------------
SOURCE ?= data/synthetic_dataset.parquet
LABEL ?= manual
SNAPSHOT_ROOT ?= data/snapshots
SNAPSHOT_ID ?=

snapshot-freeze:
	@echo "==> Freezing snapshot of $(SOURCE) (label=$(LABEL))"
	$(PYTHON) - <<'EOF'
from pathlib import Path
from data.reproducibility import DatasetSnapshot
snap = DatasetSnapshot(snapshot_root=Path("$(SNAPSHOT_ROOT)"))
m = snap.freeze(Path("$(SOURCE)"), label="$(LABEL)")
print(f"Snapshot created: {m.snapshot_id}")
print(f"  sha256   : {m.sha256}")
print(f"  rows     : {m.row_count}")
print(f"  columns  : {m.columns}")
EOF

snapshot-list:
	@echo "==> Listing snapshots under $(SNAPSHOT_ROOT)"
	$(PYTHON) - <<'EOF'
from pathlib import Path
from data.reproducibility import SnapshotRegistry
reg = SnapshotRegistry(Path("$(SNAPSHOT_ROOT)"))
manifests = reg.list_all()
if not manifests:
    print("No snapshots found.")
else:
    for m in manifests:
        print(f"  {m.snapshot_id}  label={m.label!r}  rows={m.row_count}  sha256={m.sha256[:12]}...")
EOF

snapshot-verify:
	@if [ -z "$(SNAPSHOT_ID)" ]; then echo "Error: SNAPSHOT_ID is required.  Usage: make snapshot-verify SNAPSHOT_ID=<id>"; exit 1; fi
	@echo "==> Verifying snapshot $(SNAPSHOT_ID)"
	$(PYTHON) - <<'EOF'
from pathlib import Path
from data.reproducibility import DatasetSnapshot
snap = DatasetSnapshot(snapshot_root=Path("$(SNAPSHOT_ROOT)"))
ok = snap.verify("$(SNAPSHOT_ID)")
print("Integrity OK" if ok else "Integrity FAILED")
EOF

# ---------------------------------------------------------------------------
# Issue #534 — Model run comparison
#
# Usage:
#   make run-compare BASELINE=run_20240601 CANDIDATE=run_20240701 RUNS_DIR=models
#   make run-compare-all RUNS_DIR=models
# ---------------------------------------------------------------------------
BASELINE ?=
CANDIDATE ?=
RUNS_DIR ?= models
COMPARE_TOLERANCE ?= 0.01

run-compare:
	@if [ -z "$(BASELINE)" ] || [ -z "$(CANDIDATE)" ]; then \
		echo "Error: BASELINE and CANDIDATE are required."; \
		echo "Usage: make run-compare BASELINE=run_A CANDIDATE=run_B RUNS_DIR=models"; \
		exit 1; \
	fi
	@echo "==> Comparing runs $(BASELINE) → $(CANDIDATE) (tolerance=$(COMPARE_TOLERANCE))"
	$(PYTHON) - <<'EOF'
from pathlib import Path
from evaluation.run_comparator import ModelRunComparator
comp = ModelRunComparator(runs_dir=Path("$(RUNS_DIR)"), metrics_filename="metrics.json")
report = comp.compare("$(BASELINE)", "$(CANDIDATE)", regression_tolerance=float("$(COMPARE_TOLERANCE)"))
print(report.summary())
out = Path("reports/run_comparison_$(BASELINE)_vs_$(CANDIDATE).json")
report.save(out)
print(f"Report saved to {out}")
EOF

run-compare-all:
	@echo "==> Comparing all consecutive runs under $(RUNS_DIR)"
	$(PYTHON) - <<'EOF'
from pathlib import Path
from evaluation.run_comparator import ModelRunComparator
comp = ModelRunComparator(runs_dir=Path("$(RUNS_DIR)"), metrics_filename="metrics.json")
reports = comp.compare_all(regression_tolerance=float("$(COMPARE_TOLERANCE)"))
if not reports:
    print("No consecutive run pairs found.")
else:
    for r in reports:
        print(r.summary())
EOF
