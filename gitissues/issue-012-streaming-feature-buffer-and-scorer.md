# Build Streaming Feature Buffer and Scorer — Real-Time Pipeline Phase 1

**Label:** `advanced` | `streaming` | `detection` | `infrastructure`
**Difficulty:** Advanced
**Area:** new `streaming/feature_buffer.py`, new `streaming/streaming_scorer.py`, `ingestion/horizon_streamer.py`

> **This is Phase 1 of 2.** It delivers the per-wallet rolling feature buffer and the thread-safe scoring wrapper. Phase 2 (Issue #016) adds the alert dispatcher, WebSocket server, and the `scripts/stream.py` entrypoint. You can start this issue immediately; Phase 2 is blocked on this one being merged.
>
> **Blocks:** Issue #016 (Alert Dispatcher, WebSocket Server, and Streaming Entrypoint) depends on the `FeatureBuffer` and `StreamingScorer` classes delivered here.

---

## Summary

`ingestion/horizon_streamer.py` already streams live `Trade` objects from the Stellar Horizon SSE API, but the objects are never fed to the detection pipeline in real time. The batch loader (`historical_loader.py`) is used instead, meaning new wash trading can go undetected for minutes or hours between pipeline runs.

This issue builds the two core stateful components needed for real-time detection:

1. **`FeatureBuffer`** — a thread-safe, per-wallet rolling window of recent `Trade` objects. Multiple pair-streaming threads write to it concurrently; the scorer reads from it.
2. **`StreamingScorer`** — a thin, thread-safe wrapper around `RiskScorer` that builds a feature row from the buffer and calls the ensemble on every new trade.

These two classes are the foundation the rest of the streaming pipeline (Phase 2) is built on.

---

## Detailed Description

### Architecture context (full pipeline)

```
Horizon SSE Stream (per pair)          ← already implemented
        │
        ▼
  FeatureBuffer    ←── THIS ISSUE: per-wallet rolling deque, thread-safe
  (rolling N trades)
        │ updated feature row
        ▼
  StreamingScorer  ←── THIS ISSUE: RiskScorer wrapper, thread-safe
        │ RiskScore dict
        ▼
  AlertDispatcher  ←── Phase 2 (Issue #016)
```

### `streaming/feature_buffer.py` — `FeatureBuffer`

```python
class FeatureBuffer:
    def __init__(self, max_trades: int = 1000): ...

    def update(self, trade: Trade) -> None:
        """Add trade to buffer for both base_account and counter_account.
        Evicts oldest trade when max_trades is exceeded per wallet."""

    def get_feature_row(self, wallet: str) -> pd.Series | None:
        """Build and return the feature row for wallet using build_feature_vector.
        Returns None if the wallet has no trades in the buffer."""

    def wallet_trade_count(self, wallet: str) -> int:
        """Return number of trades currently buffered for wallet."""

    def all_wallets(self) -> list[str]:
        """Return all wallets currently tracked in the buffer."""
```

**Thread safety:** Each wallet's deque is protected by its own `threading.Lock`. The dict of per-wallet locks is itself protected by a top-level `threading.RLock` (for lock creation). This design allows concurrent writes for **different** wallets without serialisation, while still protecting concurrent writes to the **same** wallet's deque.

**Memory:** Enforce `max_trades` per wallet. When a new trade is added and the deque is at capacity, `popleft()` the oldest entry before appending. Add a `streaming/buffer_stats.py` helper that logs buffer sizes on a configurable interval (default 60 s).

**Benford window computation:** `get_feature_row` calls `build_feature_vector` from `detection/feature_engineering.py` directly on the current deque contents — it does **not** pre-aggregate. This is correct but means Benford window computation is `O(n)` on every call. This is acceptable for buffers of ≤ 1000 trades; optimisation is out of scope for Phase 1.

### `streaming/streaming_scorer.py` — `StreamingScorer`

```python
MIN_TRADES_FOR_SCORING = 20  # configurable via Config

class StreamingScorer:
    def __init__(self, model_dir: str | None = None): ...

    def score_wallet(self, wallet: str, buffer: FeatureBuffer) -> dict | None:
        """Build feature row from buffer and score.
        Returns None if wallet has < MIN_TRADES_FOR_SCORING trades.
        Returns RiskScore dict {score, benford_flag, ml_flag, confidence} otherwise."""
```

`RiskScorer.score()` is stateless (no mutable model state per call), so `StreamingScorer` needs no additional locking — concurrent calls from multiple threads are safe.

Add `Config.MIN_TRADES_FOR_SCORING: int = int(os.getenv("MIN_TRADES_FOR_SCORING", "20"))` to `config.py`.

### New package: `streaming/__init__.py`

Create `streaming/` as a proper package with an empty `__init__.py`. Do **not** implement `AlertDispatcher`, `ws_server.py`, or `pipeline.py` here — those belong in Phase 2.

### Files to create / modify

| File | Action |
|---|---|
| `streaming/__init__.py` | New — empty package init |
| `streaming/feature_buffer.py` | New — `FeatureBuffer` class |
| `streaming/streaming_scorer.py` | New — `StreamingScorer` class |
| `streaming/buffer_stats.py` | New — periodic buffer size logger |
| `config.py` | Add `MIN_TRADES_FOR_SCORING` |

---

## Requirements

### Functional
- `FeatureBuffer.update()` must add the trade to both `base_account`'s buffer and `counter_account`'s buffer (both wallets are involved in each trade).
- `get_feature_row()` must return `None` (not raise) when a wallet has no buffered trades.
- `StreamingScorer.score_wallet()` must return `None` when `buffer.wallet_trade_count(wallet) < MIN_TRADES_FOR_SCORING`.

### Thread safety
- Passing the concurrent write test (10 threads × 100 trades, same wallet) must produce no `RuntimeError`, no data corruption, and a final buffer length ≤ `max_trades`.
- `get_feature_row()` must acquire the wallet's lock before reading the deque (prevents torn reads mid-eviction).

### Memory
- After `max_trades + 1` updates to one wallet, `wallet_trade_count(wallet)` must equal `max_trades` exactly.

### Security
- No new credentials or external API calls.

### Documentation
- Add `streaming/` to the Repository Structure section of `README.md`.
- Add `MIN_TRADES_FOR_SCORING` to `.env.example`.
- Docstrings on all public methods.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_feature_buffer.py` and `tests/test_streaming_scorer.py`:

**`tests/test_feature_buffer.py`:**

1. **`test_update_adds_to_both_accounts`** — one trade between wallets A and B; assert both `A` and `B` appear in `buffer.all_wallets()`.
2. **`test_evicts_oldest_trade_at_capacity`** — add `max_trades + 1` trades for one wallet; assert `wallet_trade_count == max_trades` and the buffer's oldest trade is the second one added (not the first).
3. **`test_get_feature_row_returns_none_for_unknown_wallet`** — call `get_feature_row("GUNKNOWN...")` on an empty buffer; assert `None` is returned.
4. **`test_get_feature_row_returns_series_with_expected_columns`** — add 25 trades for wallet A; assert `get_feature_row("A")` is a `pd.Series` containing `benford_chi_square_1h` and `counterparty_concentration_ratio`.
5. **`test_concurrent_writes_no_corruption`** — 10 threads each write 100 trades for the same wallet concurrently; assert no exception and final `wallet_trade_count <= max_trades`.
6. **`test_concurrent_writes_different_wallets_no_deadlock`** — 10 threads each writing to a different wallet; assert all complete within 5 seconds.

**`tests/test_streaming_scorer.py`:**

7. **`test_score_wallet_returns_none_below_min_trades`** — buffer with 5 trades, `MIN_TRADES_FOR_SCORING=20`; assert `score_wallet` returns `None`.
8. **`test_score_wallet_returns_score_at_threshold`** — buffer with exactly 20 trades and mocked `RiskScorer`; assert result is a dict with `score`, `benford_flag`, `ml_flag`, `confidence`.
9. **`test_score_wallet_returns_score_above_threshold`** — buffer with 50 trades; assert result is non-None.
10. **`test_scorer_no_models_raises_runtime_error`** — point `MODEL_DIR` at empty directory; assert `RuntimeError` is raised during `StreamingScorer.__init__` (propagated from `RiskScorer`).

Run with: `pytest tests/test_feature_buffer.py tests/test_streaming_scorer.py -v`

All ten tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python concurrency / data pipeline engineering. Deep familiarity with `threading.Lock`, `collections.deque`, and thread-safe data structure design is required. No Stellar SDK or WebSocket expertise needed for this phase.

When commenting to claim this issue, please include:
- Your experience designing thread-safe data structures in Python.
- Whether you have read `ingestion/horizon_streamer.py`, `detection/feature_engineering.py`, and `detection/model_inference.py` in full.
- Your approach to per-wallet lock granularity (2–3 sentences on why per-wallet locks are preferable to a single global lock here).

Completing this issue unlocks Phase 2 (Issue #016) and makes LedgerLens capable of real-time detection for the first time.
