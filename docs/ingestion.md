# Ingestion

## Distributed rate limiting for Horizon REST calls

When multiple ingestion workers run in parallel, each making independent
Horizon REST calls, their combined request rate can exceed Horizon's
per-IP limit (100 req/s) and trigger 429 responses with dropped data.
`ingestion/rate_limiter.py` enforces one global cap shared across all
workers.

### Architecture

```
 worker 1 ─┐
 worker 2 ─┼─► TokenBucketLimiter.acquire() ─► Redis (shared token bucket) ─► Horizon
 worker N ─┘                                         │
                                         WATCH/MULTI optimistic transaction
                                         guarantees atomic token decrement
```

* `TokenBucketLimiter` stores `tokens` / `updated_at` in a single Redis hash
  and mutates it through a `WATCH`/`MULTI` optimistic transaction, so two
  workers can never decrement the same token.
* `HORIZON_MAX_RPS` (config.py, default 80, capped at 100) is the global
  budget; the bucket refills continuously at that rate up to its capacity.
* `ingestion/horizon_fetcher.fetch()` wraps a Horizon call: it acquires a
  token first, then on a 429 response backs off exponentially (1s, 2s, 4s,
  ... capped at 60s) with +/-20% jitter and retries up to
  `HORIZON_MAX_RETRIES` (default 5) times. Any other 4xx (e.g. 403) is
  raised immediately without retry.
* `ingestion/historical_loader.py`'s `_fetch_page` routes through
  `horizon_fetcher.fetch()` as the reference integration point for paginated
  REST calls.

### Redis dependency

Requires a reachable Redis instance via `REDIS_URL` (default
`redis://localhost:6379/0`).

### Degraded mode

If Redis is unreachable -- at startup or on any later call -- the limiter
logs a warning once and grants every request immediately rather than
blocking ingestion on a rate-limiter outage. This sacrifices the global cap
under Redis downtime in favor of not stalling data collection.

## Untrusted input handling

Every trade, order-book event, and account activity record LedgerLens
ingests originates from a Horizon REST/SSE endpoint or an AMM pool
endpoint -- a network service outside this system's trust boundary. A
misbehaving relay, a MITM'd HTTP proxy, or a buggy Horizon fork can hand
back JSON that parses fine but is semantically bogus: a NaN amount, a
zero-denominator price fraction, a 300-character "asset code", an account
ID that isn't a real Stellar key, a timestamp decades in the future.
Nothing downstream (Benford analysis, the wallet graph, forensic reports)
re-validates these fields, so a bad record that isn't caught at the
boundary either crashes the ingestion worker or silently corrupts
detection output.

### The contract

`ingestion/untrusted_input.py` is the single place this validation lives.
Every loader that turns a raw external record into a `Trade` /
`OrderBookEvent` / `AccountActivity` (`ingestion/data_models.py`) passes
the result through the matching `validate_*` function before the record
is allowed to reach the rest of the pipeline:

| Domain model | Validator | Called from |
|---|---|---|
| `Trade` | `validate_trade` | `historical_loader.load_trades`, `horizon_streamer.stream_trades`, `amm_pool_loader.load_amm_pool_trades` / `stream_amm_pool_trades` |
| `OrderBookEvent` | `validate_orderbook_event` | `orderbook_loader.load_orderbook_events` |
| `AccountActivity` | `validate_account_activity` | `account_activity_loader.load_account_activity` |

Each validator checks, and raises `UntrustedInputError` (a `ValueError`
subclass) on the first field that fails:

* **Account IDs** (`base_account`, `counter_account`, `account`,
  `account_id`, `funding_account`) must be a structurally valid Stellar
  ed25519 public key per `stellar_sdk.strkey.StrKey` (checksum included --
  a regex alone can't catch a corrupted checksum).
* **Asset codes** must satisfy Stellar's own 1-12 alphanumeric-character
  rule (`stellar_sdk.Asset.check_if_asset_code_is_valid`), with `"XLM"` /
  `"native"` accepted as this repo's sentinel for the native asset.
* **Amounts and prices** must be finite (no NaN/Inf) and non-negative;
  `Trade.base_amount` / `counter_amount` / `price` must additionally be
  strictly positive (a zero-amount trade or a zero price is not a real
  trade -- it is what a poisoned or malformed record most often looks
  like).
* **Timestamps** must fall between the Stellar public network's genesis
  (2015-09-30) and a few minutes into the future (small clock-skew
  allowance).
* **String fields** (`trade_id`, `event_id`, account IDs, asset codes) are
  capped at `MAX_STRING_FIELD_LENGTH` (128 chars) as a defense-in-depth
  guard against a record designed to waste memory/CPU downstream (pandas,
  logging, forensic report rendering).

`safe_ratio(n, d, default=0.0)` centralizes the one recurring crash we
found while building this: Horizon encodes `price` as an `{"n": ..., "d":
...}` fraction, and a zero or malformed denominator previously raised an
unguarded `ZeroDivisionError` inside `horizon_streamer._to_trade` --
crashing the whole SSE stream on one bad tick. All four loaders now
compute untrusted price fractions through `safe_ratio` instead of
open-coding `float(n) / float(d)`.

### Failure handling: skip, log, continue -- never crash the batch

Validation failures are not fatal to the surrounding page or stream. Each
loop that calls a `validate_*` function catches `UntrustedInputError`
(alongside `pydantic.ValidationError` for structural issues and the raw
`KeyError`/`ValueError` a malformed record can still raise before a
`Trade`/`OrderBookEvent` is even constructed), logs a warning identifying
the record (trade/event id or paging token) and the failing field, and
continues to the next record. One poisoned record degrades to "one row
missing," not "ingestion worker down."

### Diagnostics

If `prometheus_client` is installed, every rejection increments
`ledgerlens_untrusted_records_rejected_total{source, field}` --
`source` identifies the loader (`historical_loader`, `horizon_streamer`,
`orderbook_loader`, `account_activity_loader`, `amm_pool_loader`,
`amm_pool_loader_stream`) and `field` identifies which validator caught
the problem, so a sustained spike in one label pair (e.g. a compromised
or misbehaving Horizon mirror producing a wave of invalid account IDs) is
directly actionable without grepping logs.

### What this does *not* change

The `validate_*` functions run only inside the loaders above -- they are
not added as `pydantic` field constraints on `Trade` / `OrderBookEvent` /
`AccountActivity` themselves. Those models remain constructible with
arbitrary field values (as `tests/factories.py` and much of the test
suite already do) for anything that isn't crossing the untrusted-external
boundary. This keeps the security contract scoped to where it actually
matters -- data arriving from Horizon/AMM -- without changing the public
shape of the domain models themselves.
