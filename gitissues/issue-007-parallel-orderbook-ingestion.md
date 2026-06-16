# Parallelize Order-Book Event Ingestion Using `concurrent.futures`

**Label:** `intermediate` | `performance` | `ingestion`
**Difficulty:** Intermediate
**Area:** `ingestion/orderbook_loader.py`, `run_pipeline.py`

---

## Summary

`load_accounts_orderbook_events` in `ingestion/orderbook_loader.py` fetches order-book history for each wallet sequentially. For a pipeline run that scores 500+ wallets, this means 500+ sequential HTTP round-trips to Horizon — a dominant source of pipeline latency. Each call is independent and can be parallelized.

This issue asks you to replace the sequential loop in `load_accounts_orderbook_events` with a `concurrent.futures.ThreadPoolExecutor` implementation, making the ingestion layer dramatically faster while preserving the same output DataFrame contract and keeping the existing retry/backoff behaviour intact.

---

## Detailed Description

### Current code (sequential)

```python
def load_accounts_orderbook_events(account_ids: list[str]) -> pd.DataFrame:
    frames = [orderbook_events_to_dataframe(load_orderbook_events(a)) for a in account_ids]
    if not frames:
        return orderbook_events_to_dataframe(iter([]))
    return pd.concat(frames, ignore_index=True)
```

### Required change

Replace the list comprehension with a `ThreadPoolExecutor`. Key considerations:

1. **Thread safety**: `stellar_sdk.Server` creates a new HTTP session per instantiation; `load_orderbook_events` already creates a new `Server` per call, so no shared state issue exists. Do **not** introduce a shared `Server` singleton.

2. **Max workers**: Parameterise `max_workers` with a default of `10`. Expose this as a config value (`Config.ORDERBOOK_MAX_WORKERS`) and as a CLI flag `--orderbook-workers N` in `run_pipeline.py`.

3. **Error isolation**: If one account's fetch raises (after all retry attempts), log a warning and continue — the failed account contributes an empty DataFrame, not a full pipeline crash. This matches the current sequential behaviour where one failure already propagates as an exception; the parallel version should downgrade this to a warning.

4. **Order independence**: `pd.concat` over futures results produces the same schema regardless of completion order.

5. **Progress logging**: Log a progress message every 50 accounts (e.g. `"Fetched order-book events for 100/523 accounts"`) so operators can monitor long-running ingestion.

### Files to modify

| File | Change |
|---|---|
| `ingestion/orderbook_loader.py` | Replace sequential loop with `ThreadPoolExecutor`; add `max_workers` parameter |
| `config.py` | Add `ORDERBOOK_MAX_WORKERS: int = int(os.getenv("ORDERBOOK_MAX_WORKERS", "10"))` |
| `run_pipeline.py` | Add `--orderbook-workers` CLI flag; pass it to `load_accounts_orderbook_events` |

---

## Requirements

### Functional
- The output DataFrame schema and content must be **identical** to the current sequential version for any given set of accounts. Tests must verify this.
- A single account failure (after retries) must not abort the entire fetch — log a `WARNING` and return an empty frame for that account.
- `max_workers=1` must produce behaviour equivalent to the current sequential implementation (useful for debugging).

### Performance
- With `max_workers=10`, the parallel implementation must be measurably faster than sequential for 50+ accounts (a benchmark test is not required, but the implementation must not add serialization overhead that defeats the purpose).

### Security
- No credential exposure. Horizon order-book endpoints are public.

### Thread safety
- Do **not** use a shared global `Server` instance across threads. Each `Future` must use its own `Server` instance (already the case in the current per-call pattern).

### Documentation
- Update `README.md`'s flag table to include `--orderbook-workers`.
- Add `ORDERBOOK_MAX_WORKERS` to `.env.example`.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_parallel_orderbook.py` (or expand `tests/test_orderbook.py`):

1. **`test_parallel_output_matches_sequential`** — with mocked `_fetch_page`, run both the old sequential logic and the new parallel logic on the same 5-account list; assert `pd.DataFrame.equals` on both results (after sorting by `event_id`).
2. **`test_failed_account_produces_warning_not_crash`** — mock one account to always raise `ConnectionError`; assert the returned DataFrame has the other accounts' events and a `WARNING` log entry mentioning the failed account.
3. **`test_max_workers_one_behaves_sequentially`** — run with `max_workers=1` and assert the result matches the sequential reference.
4. **`test_progress_logging_emitted`** — with 60 mocked accounts (3 per page, 20 pages), assert at least one progress log line is emitted (use `caplog`).
5. **`test_empty_account_list_returns_empty_frame`** — assert calling `load_accounts_orderbook_events([])` returns an empty DataFrame with the correct columns.

Run with: `pytest tests/test_parallel_orderbook.py -v`

All five tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python backend / concurrency. Familiarity with `concurrent.futures.ThreadPoolExecutor`, thread-safety considerations, and HTTP-heavy Python workloads is required. No ML or Stellar SDK expertise needed.

When commenting to claim this issue, please include:
- Your experience with Python concurrency (`concurrent.futures`, `asyncio`, or `threading`).
- Whether you have read `ingestion/orderbook_loader.py` and `utils/retry.py` in full.
- Any prior work on parallelizing I/O-bound Python code.

This is a high-impact performance improvement: the order-book stage is the pipeline's dominant latency contributor at scale, and parallelizing it will cut end-to-end run time significantly.
