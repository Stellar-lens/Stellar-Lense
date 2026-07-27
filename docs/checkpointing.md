# Checkpoint / Resume for Batch Pipelines

## Overview

`utils/checkpoint.py` gives long-running batch entry points — `run_pipeline.py`,
`scripts/backfill_amm_trades.py`, and future pipelines with the same shape — a
shared contract for resuming after a crash, a Ctrl-C, or an operator-triggered
stop, instead of reprocessing everything from unit 1.

It targets **batch** pipelines that iterate over a finite, enumerable list of
independent units of work (an asset pair, an AMM pool, a backtest window). It
is not for the always-on streaming service (`streaming/pipeline.py`), which
already resumes via Kafka consumer-group offsets (see
`docs/stream_replay_runbook.md`) — an unbounded stream has no "done" state to
checkpoint against.

## Why this exists

Every unit of work in these pipelines costs one or more paginated Horizon API
calls plus feature computation — rate-limited (`ingestion/rate_limiter.py`)
and, for large backfills, slow enough that a late failure is expensive to
redo. Before this, a failure on pair 7 of 10 in `run_pipeline.py`, or pool 3
of 8 in `backfill_amm_trades.py`, meant re-fetching and reprocessing
everything on the next attempt.

## Contract

```python
from utils.checkpoint import PipelineCheckpoint

ckpt = PipelineCheckpoint.load_or_create(
    path=args.checkpoint_file,
    pipeline="run_pipeline",                 # guards against pointing two
                                              # different pipelines at one file
    fingerprint_inputs={                     # everything that changes what
        "since": str(args.since),            # "done" means for a unit
        "pairs": sorted(pair_ids),
    },
    fresh=args.fresh,                        # discard + start over
)

for unit_id in ckpt.pending(all_unit_ids):   # skips already-completed units
    try:
        result = do_work(unit_id)
    except Exception as exc:
        ckpt.record_failure(unit_id, exc)    # stays pending, retried next run
        continue
    ckpt.record_success(unit_id, metadata={"rows": len(result)})
```

* **Storage**: a single JSON file, written atomically (temp file + `os.replace`)
  after every unit completes. A crash never corrupts the file and never loses
  more than the in-flight unit.
* **Fingerprinting**: `fingerprint_inputs` is hashed into the checkpoint.
  Resuming with different inputs (a different `--since`, a different pair
  list, ...) raises `CheckpointMismatchError` with a field-by-field diff of
  what changed, instead of silently mixing incompatible runs:

  ```
  CheckpointMismatchError: Checkpoint file .checkpoints/run_pipeline.json was
  created for a different run configuration.
  Changed inputs:
    since: '2024-01-01T00:00:00' -> '2024-06-01T00:00:00'
  Re-run with --fresh to discard the stale checkpoint and start over, or point
  --checkpoint-file at a new path for this configuration.
  ```
* **Failure tracking**: a failed unit is recorded (error message + attempt
  count), not silently dropped, so it is retried automatically on the next
  run. `PipelineCheckpoint.summary()` gives an at-a-glance diagnostic of what
  succeeded, what failed, and by which unit ID.
* **Artifact caching (optional)**: `record_success(unit_id, artifact_path=...)`
  lets a pipeline cache expensive per-unit output (e.g. a Parquet file of
  fetched trades) and skip recomputation entirely on resume, not just skip
  re-marking the unit done. `backfill_amm_trades.py` uses this; `run_pipeline.py`
  does not need it since a "done" pair has nothing left to reuse.
* **Corruption / schema drift**: an unparsable file or an unrecognized
  `schema_version` raises `CheckpointCorruptError` rather than being
  silently reinterpreted. `--fresh` recovers from either case.

## Opt-in, not a behavior change

Checkpointing is off by default in both integrations — pass `--checkpoint-file
<path>` to enable it. Without that flag, both scripts behave exactly as
before: an exception from any unit propagates and aborts the run.

With `--checkpoint-file` set:

* A unit already recorded complete is skipped (its expensive fetch is never
  retried).
* A unit that raises is recorded as failed and the run **continues** with the
  remaining units instead of aborting — the checkpoint is only useful if one
  bad pair/pool doesn't take down the whole batch.
* Re-running with the same `--checkpoint-file` and the same inputs resumes
  automatically; pass `--fresh` to discard it and start over.
* `--checkpoint-file` has no effect combined with `--dry-run` (nothing is
  written, so there is nothing meaningful to resume).

## Integrations

### `run_pipeline.py`

```bash
python run_pipeline.py --since 2024-01-01 --checkpoint-file .checkpoints/run_pipeline.json
# ... crashes partway through, e.g. Horizon times out on pair 7 of 10 ...
python run_pipeline.py --since 2024-01-01 --checkpoint-file .checkpoints/run_pipeline.json
# resumes: pairs 1-6 and 8-10 (if they'd already succeeded) are skipped,
# pair 7 is retried
```

Each asset pair is one unit of work covering its full Horizon fetch, feature
build, scoring, and persistence. The fingerprint covers `--since`, the
watched pair list, `--no-orderbook`, and `--no-graph` — anything that changes
what a pair's output means.

### `scripts/backfill_amm_trades.py`

```bash
python -m scripts.backfill_amm_trades --pool-ids <a> <b> <c> \
    --checkpoint-file .checkpoints/backfill_amm_trades.json
```

Each pool is one unit of work. A pool's fetched trades are cached to
`.checkpoints/backfill_amm_trades_pool_<pool_id>.parquet` the first time it
succeeds; a resumed run loads that Parquet file directly instead of
re-fetching from Horizon. A pool that returns `PoolNotFoundError` is recorded
done (not retried — it's a permanent condition, not a transient failure).

## Adding checkpointing to a new pipeline

1. Identify the unit of work — it must be independently retryable and cheap
   to enumerate up front (a list of IDs, not a stream).
2. Pick `fingerprint_inputs`: every CLI argument or config value that changes
   what "done" means for a unit. Under-including risks silently resuming
   incompatible state; over-including just means more `--fresh` reruns than
   necessary.
3. Wrap the per-unit body in try/except only when checkpointing is enabled —
   keep the checkpoint-disabled path's exception propagation unchanged so
   existing callers/tests see no behavior change.
4. If the unit produces reusable intermediate output, cache it via
   `artifact_path` next to the checkpoint file; otherwise omit it.

## Testing

* `tests/test_checkpoint.py` — the `PipelineCheckpoint` primitive in
  isolation (round-trip persistence, fingerprint mismatch diagnostics,
  corruption handling, failure/retry bookkeeping).
* `tests/test_run_pipeline_checkpoint.py` — `run_pipeline.py` resume behavior:
  skip-on-resume, failed-pair retry, `--fresh`, `--dry-run` is a no-op for
  checkpointing, and the no-`--checkpoint-file` path still aborts on any
  failure (no behavior change).
* `tests/test_backfill_amm_trades_checkpoint.py` — pool-level artifact
  caching, `PoolNotFoundError` treated as permanent, other exceptions
  recorded as retryable failures.

Run just this surface with:

```bash
pytest -q tests/test_checkpoint.py tests/test_run_pipeline_checkpoint.py \
    tests/test_backfill_amm_trades_checkpoint.py
```
