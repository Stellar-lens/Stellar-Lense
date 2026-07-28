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

## Transaction normalization contract

"Normalizing a transaction" is not one function — it's several
independently-implemented conversions that all have to agree with each
other. Property-based tests in
`tests/test_transaction_normalization_properties.py` (strategies shared via
`tests/strategies.py`) pin down the following contract so the layers can't
silently drift apart:

1. **Raw source record → `Trade`.** `ingestion/horizon_streamer.py::_to_trade`
   and `ingestion/amm_pool_loader.py::_amm_record_to_trade` each convert a
   differently-shaped raw dict (an SSE trade event vs. a liquidity-pool trade
   effect) into the same `ingestion.data_models.Trade`. Both must normalize a
   native asset (empty/absent code) to `Asset(code="XLM", issuer=None)` —
   downstream code (Benford engine, Kafka producer, per-pair metrics) assumes
   this canonical form and does not re-check it.
2. **`Trade` ↔ Avro wire record.** `ingestion/avro_codec.py::trade_to_record`/
   `record_to_trade` must round-trip every field losslessly, both as a plain
   dict conversion and through the actual binary encode/decode path used by
   the Kafka producer/worker. The one expected exception is
   `ledger_close_time`: the Avro schema encodes it as `timestamp-millis`, so
   sub-millisecond precision is truncated (floored, not rounded) on the wire.
3. **Asset pair → canonical partition/metric-label key.** Two independent
   implementations build a direction-independent "canonical pair" string:
   `ingestion/kafka_producer.py::_to_canonical_pair_id` (validates asset code
   `^[A-Z0-9]{1,12}$` / issuer `^G[A-Z0-9]{55}$` or `"native"`, then sorts) and
   `detection/per_pair_metrics.py::canonical_pair` (sorts an already-formatted
   string). They must agree: a partition key produced by the Kafka producer
   has to already be in `canonical_pair`'s canonical form, or the metrics
   layer would silently re-normalize it to something else and fragment
   `asset_pair` cardinality. Note that `ingestion.data_models.Asset.pair_id`
   is a *different*, intentionally direction-preserving format (base/counter
   order) used for the Avro `asset_pair` field — it is not interchangeable
   with either canonical-pair function above.

### Known gap: `_to_trade` has no price-division guard

`_amm_record_to_trade` wraps its `price.n / price.d` division in a
`try/except (KeyError, TypeError, ZeroDivisionError, ValueError)` and
degrades to `price=0.0` on malformed input. `_to_trade` performs the same
division unguarded. A Horizon payload with `price.d == 0` (or a missing
`price` field) currently raises an unhandled `ZeroDivisionError`/`KeyError`
out of `_to_trade`, which `stream_trades`' reconnect logic does not catch
(it only retries on `ConnectionError`/`TimeoutError`/`OSError`) — so it would
crash the SSE ingestion loop rather than degrade gracefully.

`tests/test_transaction_normalization_properties.py::test_to_trade_raises_on_zero_price_denominator`
pins this as current, intentional-for-now behavior rather than silently
patching it. Follow-up: mirror `_amm_record_to_trade`'s guard in `_to_trade`
if this is confirmed to occur in production Horizon data.
