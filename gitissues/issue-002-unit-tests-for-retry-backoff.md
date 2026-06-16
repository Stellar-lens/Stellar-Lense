# Write Unit Tests for `utils/retry.py` `retry_with_backoff` Decorator

**Label:** `good first issue` | `testing` | `utils`
**Difficulty:** Good First Issue
**Area:** `utils/retry.py` / test coverage

---

## Summary

`utils/retry.py` contains the `retry_with_backoff` decorator that wraps every Horizon API call in the ingestion layer (`ingestion/historical_loader.py`, `ingestion/orderbook_loader.py`). This module has **zero test coverage**. A broken retry decorator can cause silent data-loss or infinite loops under transient network failures.

This issue asks for a dedicated test file `tests/test_retry.py` that thoroughly covers `retry_with_backoff`'s behaviour.

---

## Detailed Description

### Current state

`utils/retry.py` implements exponential backoff with the following parameters:
- `max_attempts` — total attempts before re-raising (default 3).
- `base_delay_seconds` — initial wait before the first retry (default 1.0 s).
- `backoff_factor` — multiplier applied to delay after each retry (default 2.0).
- `exceptions` — tuple of exception types that trigger a retry (default `(Exception,)`).

The decorator is used in production on `_fetch_page` in both `historical_loader.py` and `orderbook_loader.py`, making its correctness critical.

### Why this matters

If `retry_with_backoff` re-raises on the wrong attempt count, or fails to propagate non-retriable exceptions immediately, the ingestion layer either silently drops data or hangs indefinitely in production.

### What to implement

Create `tests/test_retry.py`. Do **not** actually sleep during tests — patch `time.sleep` to make tests fast.

---

## Requirements

### Functional
- All tests must use `unittest.mock.patch("time.sleep")` (or `pytest-mock`'s `mocker.patch`) to suppress real sleeps.
- Tests must cover both `retry_with_backoff` as a decorator and as a direct call (i.e. `retry_with_backoff(...)(func)(...)`).

### Code style
- Follow the existing test style in `tests/test_benford.py` — plain `pytest` functions, no test classes.
- Line length ≤ 100 characters (`black` / `ruff` enforced).

### Documentation
- No documentation changes required for this issue.

---

## Tests Required (mandatory — all must pass)

Implement **all** of the following tests in `tests/test_retry.py`:

1. **`test_succeeds_on_first_attempt`** — the wrapped function is called exactly once and its return value is returned when no exception is raised.
2. **`test_retries_on_specified_exception`** — when the function raises the configured exception on the first two attempts and succeeds on the third, the return value is returned and `time.sleep` was called twice.
3. **`test_raises_after_max_attempts`** — when the function always raises, `pytest.raises` catches the exception after exactly `max_attempts` total calls; `time.sleep` is called `max_attempts - 1` times.
4. **`test_does_not_retry_unspecified_exception`** — when `exceptions=(ConnectionError,)` and the function raises `ValueError`, the `ValueError` propagates immediately without any retry (sleep is never called).
5. **`test_exponential_backoff_delay_sequence`** — with `base_delay_seconds=1.0` and `backoff_factor=3.0`, the delays passed to `time.sleep` are `[1.0, 3.0]` for a function that fails twice then succeeds.
6. **`test_default_max_attempts_is_three`** — using the default parameters, confirm the function is called at most 3 times before the exception propagates.
7. **`test_wraps_preserves_function_metadata`** — assert that `decorated_func.__name__` and `decorated_func.__doc__` match the original function (i.e. `functools.wraps` is applied correctly).

Run with: `pytest tests/test_retry.py -v`

All seven tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python testing. No ML or Stellar knowledge required.

When commenting to claim this issue, please include:
- Your familiarity with `pytest` and `unittest.mock`.
- Whether you have read `utils/retry.py` in full (it is under 60 lines).
- Your GitHub handle so we can assign the issue to you.

This is a great starting point if you want to contribute to test infrastructure and learn how the ingestion layer is protected against flaky network connections.
