# Blockchain Ingestion Adapters with Normalized Event Contracts

## Overview

LedgerLens ingests data from Stellar Horizon (`ingestion/horizon_fetcher.py`,
`ingestion/historical_loader.py`, `ingestion/horizon_streamer.py`) into
Stellar-specific Pydantic models (`ingestion/data_models.py`: `Trade`,
`OrderBookEvent`, `AccountActivity`). Feature engineering and detection code
consume those models directly.

That design couples every downstream consumer to Stellar's specific event
shape. Adding a second ingestion source -- an EVM bridge counterpart, a
different DEX, another Stellar-compatible network -- previously meant either
reshaping the new source's data to fit the Stellar models (lossy and
confusing) or forking feature engineering per chain (duplicative).

`ingestion/adapters/` adds a chain-agnostic **normalized event contract**
that any ingestion source can adapt into, without changing the existing
Stellar pipeline:

- **`NormalizedEvent`** (`base.py`) -- the shared contract: event id, chain,
  event type, timestamp, account/counterparty, asset(s), amount(s), and a
  `raw` passthrough for chain-specific detail that doesn't fit the
  normalized shape.
- **`ChainAdapter`** (`base.py`) -- abstract contract every adapter
  implements: `normalize(raw_event) -> NormalizedEvent`, plus a
  `normalize_batch()` helper that collects per-record failures instead of
  aborting a whole backfill batch on one bad record.
- **`AdapterValidationError`** -- raised (with chain name + truncated raw
  payload) when a raw event can't be normalized, so failures during a
  batch run are attributable to a specific record.
- **`StellarAdapter`** (`stellar_adapter.py`) -- wraps the *existing*
  `Trade` / `OrderBookEvent` / `AccountActivity` models produced by the
  current Horizon pipeline. No changes to `horizon_fetcher.py` or the raw
  Horizon response shape were required.
- **`EvmAdapter`** (`evm_adapter.py`) -- normalizes decoded EVM `Transfer`
  log events (the shape a `web3.py` event filter would hand back),
  demonstrating the contract holds for a structurally different chain.
- **`AdapterRegistry`** / **`default_registry`** (`registry.py`) -- chain
  name -> adapter lookup, so ingestion entry points resolve the adapter by
  chain string instead of hardcoding dispatch logic.

## Design tradeoffs

- **Adapters normalize; they do not fetch.** `ChainAdapter.normalize()`
  takes an already-fetched raw event/log. Network/RPC/streaming concerns
  stay in the existing transport-specific modules (`horizon_fetcher.py`,
  and a future EVM equivalent) so the normalized-contract layer has no
  transport dependencies and is trivially unit-testable with static
  fixtures.
- **`raw` is a passthrough, not an afterthought.** Every `NormalizedEvent`
  carries the original payload. Consumers that need chain-specific detail
  (a Soroban invocation's function selector, an EVM log's block number)
  can still get it without the contract growing chain-specific fields.
- **Batch normalization does not fail closed.** `normalize_batch()`
  returns `(normalized, errors)` rather than raising on the first bad
  record, matching how `ingestion/historical_loader.py` already treats
  malformed records as skippable rather than fatal during a large backfill.
- **No existing model was removed or changed.** `ingestion/data_models.py`
  is untouched; `StellarAdapter` is purely additive, so any code depending
  on `Trade`/`OrderBookEvent`/`AccountActivity` keeps working unchanged.

## Usage

```python
from ingestion.adapters import default_registry

# Normalize a single event once you know its source chain:
normalized = default_registry.normalize("stellar", trade)

# Or resolve the adapter once and normalize a batch:
adapter = default_registry.get("ethereum")
normalized_events, errors = adapter.normalize_batch(raw_transfer_logs)
for err in errors:
    logger.warning("skipped malformed event", extra={"reason": str(err)})
```

Registering a new chain:

```python
from ingestion.adapters import AdapterRegistry, ChainAdapter, NormalizedEvent

class SolanaAdapter(ChainAdapter):
    chain = "solana"

    def normalize(self, raw_event) -> NormalizedEvent:
        ...

default_registry.register(SolanaAdapter())
```

## Validation

```
pytest tests/test_ingestion_adapters.py -v
```

Covers: `NormalizedEvent`/`NormalizedAsset` contract invariants (chain
lowercasing, non-negative amount, dedup key); `StellarAdapter` normalizing
all three existing raw model types plus rejecting unsupported input and
unknown order-book actions; `EvmAdapter` normalizing a transfer log,
decimals defaulting, and missing-field/non-dict rejection;
`normalize_batch()` partial-failure handling; and `AdapterRegistry`
registration, case-insensitive lookup, missing-chain errors, and the
pre-populated `default_registry`.

## Follow-up work

- Wire `default_registry` into `ingestion/kafka_producer.py` / a future
  multi-chain streaming worker so live ingestion produces `NormalizedEvent`
  alongside (or instead of) the raw chain-specific model.
- Add a real EVM RPC/log-subscription source analogous to
  `horizon_streamer.py`, with `EvmAdapter` as its normalization step.
- Consider a `NormalizedEvent` -> feature-engineering bridge in `features/`
  once a second chain has real feature parity requirements.
