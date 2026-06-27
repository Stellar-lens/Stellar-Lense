# Active Learning Pipeline

LedgerLens uses an active learning (AL) pipeline to maximise detection
improvement per analyst-hour. Rather than retraining on all data periodically,
the pipeline selects the wallets that will teach the model the most, routes
them to an analyst for labelling, and incrementally updates the ensemble.

## Overview

```
Unscored wallet pool
        │
        ▼
  Query Strategy            ← selects N most informative wallets
        │
        ▼
  Annotation Queue          ← persists selection; analyst works through it
        │
        ▼
  scripts/annotate.py       ← terminal annotation loop
        │
        ▼
  IncrementalTrainer        ← warm-start or full retrain; rollback if AUC drops
        │
        ▼
  Updated model artifacts
```

## Query Strategies

All strategies live in `detection/active_learning/query_strategies.py`.
Each implements `select(pool, n_query, model=None) -> list[str]`.

| Strategy | Key idea | Best when |
|---|---|---|
| `least_confidence` | Lowest max predicted probability | Quick single-model baseline |
| `margin` | Smallest gap between top-2 class probs | Near-boundary wallets |
| `entropy` | Highest Shannon entropy over class probs | More nuanced uncertainty |
| `coreset` | Greedy k-center in feature space | Maximising coverage of unlabelled space |
| `badge` | k-means++ in (prob × feature) space | Combining uncertainty + diversity |
| `committee_disagreement` | Variance of RF/XGB/LightGBM probability estimates | **Default; best overall** |

Select with `--strategy <name>` in `run_active_learning.py` or set
`AL_QUERY_STRATEGY` in `.env`.

### CommitteeDisagreement efficiency

`CommitteeDisagreement` is the recommended default because it exploits the
three-model ensemble already present in LedgerLens. Wallets where all three
models disagree are those the ensemble is most uncertain about — labelling
them yields maximum information gain. This is equivalent to Query by Committee
(QBC) with KL-divergence-like disagreement measured via variance of
class-1 probability estimates.

**Statistical requirement**: `CommitteeDisagreement`-selected wallets must
have significantly higher score variance across models than randomly selected
wallets (t-test, p < 0.05). This is verified in `tests/test_query_strategies.py`.

## Annotation Workflow

### 1. Populate the queue

```bash
python -m scripts.run_active_learning \
    --pool data/unscored_wallets.parquet \
    --strategy committee_disagreement \
    --batch-size 20
```

This writes wallet IDs to `data/annotation_queue.json` with `status: pending`.

### 2. Annotate

```bash
python -m scripts.annotate --annotator-id yourname
```

For each wallet the CLI shows:

```
================================================================
Wallet : GABCD...
Score  : 87
Strategy: committee_disagreement
Asset Pair: XLM/USDC
SHAP top-3 features:
  benford_chi_square_24h=18.3  (↑ wash, contribution=+0.34)
  round_trip_frequency=0.94    (↑ wash, contribution=+0.28)
  order_cancellation_rate=0.71 (↑ wash, contribution=+0.12)

Label [w=wash, c=clean, s=skip, q=quit]:
```

Labels: `w` = wash trading (1), `c` = clean (0), `s` = skip, `q` = quit.

**Replay mode** — re-annotate previously skipped wallets:

```bash
python -m scripts.annotate --annotator-id yourname --replay
```

**Export** — write annotated rows to parquet for downstream use:

```bash
python -m scripts.annotate --export data/annotated.parquet
```

### 3. Incremental model update

```bash
python -m scripts.run_active_learning \
    --pool data/unscored_wallets.parquet \
    --update data/annotated.parquet \
    --historical data/synthetic_dataset.parquet
```

## Incremental Update Policy

`IncrementalTrainer.update(new_labelled, model_dir)` chooses one of two paths:

| Condition | Action |
|---|---|
| `len(new_labelled) < AL_RETRAIN_THRESHOLD` | **Warm-start**: re-fit XGBoost + LightGBM on new data only using the existing booster as a starting point. RandomForest unchanged. |
| `len(new_labelled) >= AL_RETRAIN_THRESHOLD` | **Full retrain**: combine historical + new data and train from scratch. |

After either path, AUC-ROC is evaluated on a held-out validation split.

**Rollback**: if AUC-ROC drops by more than `AL_ROLLBACK_AUC_DROP` (default 0.01),
the update is rejected, the original model artifacts are restored from `.bak`
copies, and their SHA-256 hashes are re-verified before serving. A rollback
event is logged and recorded in the AL update report.

Update reports are written to `reports/al_update_{timestamp}.json`:

```json
{
  "updated_at": "2026-06-20T12:00:00+00:00",
  "strategy": "warm_start",
  "n_new_samples": 18,
  "auc_before": 0.921,
  "auc_after": 0.934,
  "auc_delta": 0.013,
  "rolled_back": false
}
```

## Annotation Queue Integrity

Each annotation in `data/annotation_queue.json` is protected by an
HMAC-SHA256 computed over `wallet|label|annotator_id|annotated_at`, keyed
by `ANNOTATION_HMAC_SECRET`. Tampered annotations are rejected at export
time before they can influence a training run.

- `annotator_id` must be non-empty (accountability requirement).
- The queue file is written atomically (write to temp file, then `os.rename`).
- The queue file is created with permissions `0o600` (owner read/write only).

## Scheduled Execution

The AL loop runs weekly via `.github/workflows/active_learning.yml`.
Maintainers can also trigger it manually via `workflow_dispatch`.

## Configuration

All settings are controlled via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `AL_QUERY_STRATEGY` | `committee_disagreement` | Query strategy to use |
| `AL_BATCH_SIZE` | `20` | Number of wallets to select per run |
| `AL_RETRAIN_THRESHOLD` | `50` | Min new labels to trigger full retrain |
| `AL_ROLLBACK_AUC_DROP` | `0.01` | Max allowed AUC drop before rollback |
| `AL_QUEUE_PATH` | `data/annotation_queue.json` | Path to queue file |

## Running Tests

```bash
make test     # includes test_query_strategies, test_annotation_queue, test_incremental_trainer
make lint
```

## Multi-Annotator Workflow

### Overview

When a wallet is flagged as uncertain or sensitive, a second analyst independently
labels it (blind double-annotation). The annotation queue tracks all per-annotator
labels under a wallet's `"annotations"` list and automatically computes
inter-rater agreement metrics when at least two verified labels are present.

### Agreement Metrics

| Metric | When used | Threshold |
|---|---|---|
| **Cohen's Kappa** | Binary labels (0 = clean, 1 = wash trading) | κ ≥ 0.6 = acceptable |
| **Krippendorff's Alpha** | Ordinal / multi-class extensions; handles missing annotations | α ≥ 0.667 = acceptable (Krippendorff, 2004) |

**Why Cohen's Kappa for binary labels?**  Kappa corrects for chance agreement,
making it more reliable than raw percent agreement when label base rates are
skewed (which they are in LedgerLens: genuine wash trading is rare).

**Why Krippendorff's Alpha for multi-class?**  Alpha generalises across
measurement levels (nominal, ordinal, interval) and gracefully handles the
common case where not every wallet is annotated by every annotator — only
doubly-annotated wallets appear in the reliability matrix.

### Adding a Second Annotation

```python
from detection.active_learning.annotation_queue import AnnotationQueue

queue = AnnotationQueue()

# First annotator
queue.multi_annotate("GABCD...", label=1, annotator_id="anon-7f3a", notes="clear wash pattern")

# Second annotator (blind — different session)
queue.multi_annotate("GABCD...", label=0, annotator_id="anon-2b9c")

# Check agreement
result = queue.compute_inter_annotator_agreement("GABCD...")
# {"kappa": -1.0, "alpha": -1.0, "n_annotators": 2, "disputed": True}
```

Annotator IDs **must be pseudonymous opaque strings** (e.g. `"anon-7f3a"`).
Email addresses and real names are explicitly forbidden to protect annotator
privacy in the queue file.

### Dispute Resolution Process

1. When `compute_inter_annotator_agreement()` returns `disputed=True`
   (Kappa < 0.6), the wallet's queue status is automatically set to
   `"disputed"`.

2. A senior analyst retrieves the disputed wallets:

   ```python
   disputed = queue.get_senior_review_queue()
   # ["GABCD...", ...]
   ```

3. The senior analyst reviews the original annotations plus SHAP
   explanations and casts a tie-breaking label via `queue.annotate()`.

4. The resolved label is included in the next `export_labelled()` run and
   used for model retraining.

### Grafana Dashboard

A **"Inter-annotator Kappa (rolling)"** panel is available in the
`LedgerLens Kafka Streaming` Grafana dashboard (`monitoring/grafana/dashboards/ledgerlens-kafka.json`).
It plots the mean Cohen's Kappa over time (Prometheus metric: `inter_annotator_kappa`)
and the cumulative count of disputed wallets (`inter_annotator_disputed_total`).
Threshold lines at κ = 0.4 (red), 0.6 (yellow), and 0.8 (green) give instant
visual feedback on annotation quality.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `DISPUTE_KAPPA_THRESHOLD` | `0.6` | Kappa below which a wallet is routed to senior review |
