"""Property-based coverage for the transaction-normalization contract.

"Transaction normalization" spans several independently-implemented layers
that all need to agree on the same canonical shape:

  1. Raw source record -> ``Trade``     (ingestion/horizon_streamer.py,
                                          ingestion/amm_pool_loader.py)
  2. ``Trade`` <-> Avro wire record      (ingestion/avro_codec.py)
  3. Asset pair -> canonical partition/  (ingestion/kafka_producer.py,
     metric-label key                    detection/per_pair_metrics.py)

Hand-picked example tests already cover each of these in isolation (see
``tests/test_kafka_partitioning.py``, ``tests/test_per_pair_metrics.py``,
``tests/test_kafka_producer.py``). This module generalises those examples
into properties that hold for *any* valid input, and adds the cross-module
consistency checks that no single-function unit test can express — e.g.
whether two independently-implemented "canonical pair id" builders actually
agree with each other, and whether two independently-implemented raw-to-Trade
converters normalize the native asset the same way.

See ``docs/ingestion.md`` ("Transaction normalization contract") for the
invariants under test and known gaps.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from detection.per_pair_metrics import canonical_pair
from ingestion.amm_pool_loader import _amm_record_to_trade
from ingestion.avro_codec import (
    deserialize,
    load_schema,
    record_to_trade,
    serialize,
    trade_to_record,
)
from ingestion.horizon_streamer import _to_trade
from ingestion.kafka_producer import _to_canonical_pair_id, sanitise_pair
from tests.strategies import (
    asset_codes,
    invalid_asset_codes,
    invalid_issuers,
    issuers,
    non_empty_text,
    raw_amm_pool_records,
    raw_horizon_trade_records,
    trades,
)

# ---------------------------------------------------------------------------
# 1. Trade <-> Avro wire format round trip
# ---------------------------------------------------------------------------


@given(trade=trades())
@settings(max_examples=200)
def test_trade_to_record_round_trip_without_wire_encoding(trade):
    """record_to_trade(trade_to_record(t)) reconstructs an equivalent Trade.

    This is the in-memory half of the contract: converting to the Avro record
    dict and back must be lossless, independent of the binary encoding.
    """
    record = trade_to_record(trade)
    rebuilt = record_to_trade(record)

    assert rebuilt.trade_id == trade.trade_id
    assert rebuilt.base_account == trade.base_account
    assert rebuilt.counter_account == trade.counter_account
    assert rebuilt.base_amount == trade.base_amount
    assert rebuilt.counter_amount == trade.counter_amount
    assert rebuilt.price == trade.price
    assert rebuilt.ledger_close_time == trade.ledger_close_time
    assert rebuilt.base_asset == trade.base_asset
    assert rebuilt.counter_asset == trade.counter_asset


@given(trade=trades())
@settings(max_examples=200)
def test_trade_avro_binary_round_trip_is_lossless(trade):
    """Trade -> Avro record -> binary bytes -> record -> Trade preserves every field.

    Exercises the actual wire path used by the Kafka producer/worker, not just
    the in-memory dict conversion. ``ledger_close_time`` is generated
    millisecond-aligned (see tests/strategies.py) so truncation by Avro's
    ``timestamp-millis`` logical type does not lose information here.
    """
    schema = load_schema()
    record = trade_to_record(trade)

    encoded = serialize(record, schema)
    decoded = deserialize(encoded, schema)
    rebuilt = record_to_trade(decoded)

    assert rebuilt.trade_id == trade.trade_id
    assert rebuilt.base_account == trade.base_account
    assert rebuilt.counter_account == trade.counter_account
    assert rebuilt.base_amount == trade.base_amount
    assert rebuilt.counter_amount == trade.counter_amount
    assert rebuilt.price == trade.price
    assert rebuilt.ledger_close_time == trade.ledger_close_time
    assert rebuilt.base_asset == trade.base_asset
    assert rebuilt.counter_asset == trade.counter_asset


@given(trade=trades(), extra_micros=st.integers(min_value=1, max_value=999))
@settings(max_examples=50)
def test_avro_round_trip_truncates_sub_millisecond_precision(trade, extra_micros):
    """Sub-millisecond precision is truncated, not rounded or rejected, on the wire.

    ``timestamp-millis`` only has millisecond resolution — documenting the
    truncation direction (floor, not round) so a future schema change that
    accidentally rounds is caught.
    """
    trade = trade.model_copy(
        update={"ledger_close_time": trade.ledger_close_time.replace(microsecond=extra_micros)}
    )
    schema = load_schema()
    record = trade_to_record(trade)
    decoded = deserialize(serialize(record, schema), schema)
    rebuilt = record_to_trade(decoded)

    expected_micros = (trade.ledger_close_time.microsecond // 1000) * 1000
    assert rebuilt.ledger_close_time.microsecond == expected_micros
    assert rebuilt.ledger_close_time.replace(microsecond=0) == trade.ledger_close_time.replace(
        microsecond=0
    )


# ---------------------------------------------------------------------------
# 2. Canonical asset-pair-id construction (ingestion/kafka_producer.py)
# ---------------------------------------------------------------------------


@given(
    code_a=asset_codes,
    issuer_a=issuers,
    code_b=asset_codes,
    issuer_b=issuers,
)
@settings(max_examples=200)
def test_canonical_pair_id_is_order_invariant(code_a, issuer_a, code_b, issuer_b):
    """Swapping asset A and asset B never changes the resulting partition key.

    This is the whole point of `_to_canonical_pair_id`: both trade directions
    of the same pair must land on the same Kafka partition.
    """
    issuer_a_str = issuer_a or "native"
    issuer_b_str = issuer_b or "native"

    forward = _to_canonical_pair_id(code_a, issuer_a_str, code_b, issuer_b_str)
    reverse = _to_canonical_pair_id(code_b, issuer_b_str, code_a, issuer_a_str)

    assert forward == reverse


@given(
    code_a=asset_codes,
    issuer_a=issuers,
    code_b=asset_codes,
    issuer_b=issuers,
)
@settings(max_examples=200)
def test_canonical_pair_id_is_deterministic(code_a, issuer_a, code_b, issuer_b):
    """Calling the builder twice with identical input always yields identical output."""
    issuer_a_str = issuer_a or "native"
    issuer_b_str = issuer_b or "native"

    first = _to_canonical_pair_id(code_a, issuer_a_str, code_b, issuer_b_str)
    second = _to_canonical_pair_id(code_a, issuer_a_str, code_b, issuer_b_str)

    assert first == second


@given(
    code_a=asset_codes,
    issuer_a=issuers,
    code_b=asset_codes,
    issuer_b=issuers,
)
@settings(max_examples=200)
def test_canonical_pair_id_format_contract(code_a, issuer_a, code_b, issuer_b):
    """Output always has the shape CODE:ISSUER/CODE:ISSUER, alphabetically sorted."""
    issuer_a_str = issuer_a or "native"
    issuer_b_str = issuer_b or "native"

    pair_id = _to_canonical_pair_id(code_a, issuer_a_str, code_b, issuer_b_str)

    left, sep, right = pair_id.partition("/")
    assert sep == "/"
    assert left.count(":") == 1
    assert right.count(":") == 1
    assert sorted([left, right]) == [left, right]


@given(invalid_code=invalid_asset_codes, other_code=asset_codes, other_issuer=issuers)
@settings(max_examples=100)
def test_canonical_pair_id_rejects_invalid_asset_code(invalid_code, other_code, other_issuer):
    """An invalid asset code is always rejected, regardless of the other (valid) asset."""
    with pytest.raises(ValueError):
        _to_canonical_pair_id(invalid_code, "native", other_code, other_issuer or "native")


@given(invalid_issuer=invalid_issuers, other_code=asset_codes, other_issuer=issuers)
@settings(max_examples=100)
def test_canonical_pair_id_rejects_invalid_issuer(invalid_issuer, other_code, other_issuer):
    """An invalid issuer is always rejected, regardless of the other (valid) asset."""
    with pytest.raises(ValueError):
        _to_canonical_pair_id("USDC", invalid_issuer, other_code, other_issuer or "native")


# ---------------------------------------------------------------------------
# 3. sanitise_pair (Kafka-topic-safe suffix)
# ---------------------------------------------------------------------------


@given(asset_pair=non_empty_text)
@settings(max_examples=200)
def test_sanitise_pair_output_charset_is_topic_safe(asset_pair):
    """Sanitised output only ever contains Kafka-topic-safe characters."""
    sanitised = sanitise_pair(asset_pair)
    assert all(c.isalnum() or c in "._-" for c in sanitised)


@given(asset_pair=non_empty_text)
@settings(max_examples=200)
def test_sanitise_pair_is_idempotent(asset_pair):
    """Sanitising an already-sanitised string is a no-op."""
    once = sanitise_pair(asset_pair)
    twice = sanitise_pair(once)
    assert once == twice


@given(asset_pair=non_empty_text)
@settings(max_examples=200)
def test_sanitise_pair_has_no_boundary_underscores(asset_pair):
    """Sanitised output never starts or ends with the '_' replacement character."""
    sanitised = sanitise_pair(asset_pair)
    assert sanitised == sanitised.strip("_")


# ---------------------------------------------------------------------------
# 4. per_pair_metrics.canonical_pair
# ---------------------------------------------------------------------------


@given(
    code_a=asset_codes,
    issuer_a=issuers,
    code_b=asset_codes,
    issuer_b=issuers,
)
@settings(max_examples=200)
def test_metrics_canonical_pair_is_order_invariant(code_a, issuer_a, code_b, issuer_b):
    """detection.per_pair_metrics.canonical_pair agrees on A/B vs B/A, generalising
    the single hand-picked example in tests/test_per_pair_metrics.py."""
    part_a = f"{code_a}:{issuer_a or 'native'}"
    part_b = f"{code_b}:{issuer_b or 'native'}"

    forward = canonical_pair(f"{part_a}/{part_b}")
    reverse = canonical_pair(f"{part_b}/{part_a}")

    assert forward == reverse


@given(
    code_a=asset_codes,
    issuer_a=issuers,
    code_b=asset_codes,
    issuer_b=issuers,
)
@settings(max_examples=200)
def test_metrics_canonical_pair_is_idempotent(code_a, issuer_a, code_b, issuer_b):
    """Re-normalising an already-canonical pair string is a no-op."""
    part_a = f"{code_a}:{issuer_a or 'native'}"
    part_b = f"{code_b}:{issuer_b or 'native'}"
    pair = f"{part_a}/{part_b}"

    assert canonical_pair(canonical_pair(pair)) == canonical_pair(pair)


# ---------------------------------------------------------------------------
# 5. Cross-module consistency: the two independent canonical-pair builders
#    must agree, or metrics/partitioning silently fragment by asset-pair
#    direction.
# ---------------------------------------------------------------------------


@given(
    code_a=asset_codes,
    issuer_a=issuers,
    code_b=asset_codes,
    issuer_b=issuers,
)
@settings(max_examples=200)
def test_kafka_partition_key_is_already_metrics_canonical(code_a, issuer_a, code_b, issuer_b):
    """kafka_producer's partition key is a fixed point of per_pair_metrics.canonical_pair.

    ingestion/kafka_producer.py and detection/per_pair_metrics.py implement
    "canonical asset pair" independently. If they ever disagree on sort order
    or format, a partition key built by the producer would get re-normalised
    to something *different* by the metrics layer, silently doubling metric
    cardinality for every pair. This property is the regression guard for
    that failure mode.
    """
    issuer_a_str = issuer_a or "native"
    issuer_b_str = issuer_b or "native"

    partition_key = _to_canonical_pair_id(code_a, issuer_a_str, code_b, issuer_b_str)

    assert canonical_pair(partition_key) == partition_key


# ---------------------------------------------------------------------------
# 6. Raw source record -> Trade: native-asset normalization must agree across
#    ingestion sources (horizon_streamer vs amm_pool_loader).
# ---------------------------------------------------------------------------


@given(record=raw_horizon_trade_records())
@settings(max_examples=100)
def test_to_trade_normalizes_native_asset_fields(record):
    """_to_trade always canonicalizes a native (empty-code) asset to XLM/None."""
    trade = _to_trade(record)

    if not record["base_asset_code"]:
        assert trade.base_asset.code == "XLM"
        assert trade.base_asset.issuer is None
    if not record["counter_asset_code"]:
        assert trade.counter_asset.code == "XLM"
        assert trade.counter_asset.issuer is None


@given(record=raw_amm_pool_records())
@settings(max_examples=100)
def test_amm_record_to_trade_normalizes_native_asset_fields(record):
    """_amm_record_to_trade normalizes native assets identically to _to_trade.

    Both converters take differently-shaped raw records (SSE trade event vs.
    liquidity-pool trade effect) but must produce the *same* canonical
    representation of "native XLM" for downstream code (Benford engine,
    kafka_producer, per_pair_metrics) to treat them interchangeably.
    """
    trade = _amm_record_to_trade(record)

    if not record["base_asset_code"]:
        assert trade.base_asset.code == "XLM"
        assert trade.base_asset.issuer is None
    if not record["counter_asset_code"]:
        assert trade.counter_asset.code == "XLM"
        assert trade.counter_asset.issuer is None


# ---------------------------------------------------------------------------
# 7. Known fragility, pinned deliberately (not silently fixed — see PR notes
#    and docs/ingestion.md). A future intentional fix must update these tests.
# ---------------------------------------------------------------------------


def test_to_trade_raises_on_zero_price_denominator():
    """_to_trade has no guard around the price n/d division.

    Unlike ``_amm_record_to_trade`` (which catches ZeroDivisionError/KeyError/
    ValueError and degrades to ``price=0.0``), ``_to_trade`` performs the
    division unguarded. A malformed or historical Horizon payload with
    ``price.d == 0`` currently crashes the SSE ingestion loop with an
    unhandled ``ZeroDivisionError`` (``stream_trades`` only catches
    ``ConnectionError``/``TimeoutError``/``OSError``). This test pins the
    *current* behaviour deliberately rather than silently patching it, so a
    future fix consciously updates this test alongside the guard.
    """
    record = {
        "id": "1",
        "ledger_close_time": datetime(2024, 1, 1).isoformat(),
        "base_account": "G" + "A" * 55,
        "counter_account": "G" + "B" * 55,
        "base_asset_code": "USDC",
        "base_asset_issuer": "G" + "C" * 55,
        "counter_asset_code": None,
        "counter_asset_issuer": None,
        "base_amount": 100.0,
        "counter_amount": 50.0,
        "price": {"n": 1, "d": 0},
    }

    with pytest.raises(ZeroDivisionError):
        _to_trade(record)


@given(
    price_raw=st.one_of(
        st.just({}),
        st.just({"n": 1}),
        st.just({"n": 1, "d": 0}),
        st.just({"n": "not-a-number", "d": 1}),
        st.none(),
    )
)
@settings(max_examples=20)
def test_amm_record_to_trade_degrades_gracefully_on_malformed_price(price_raw):
    """_amm_record_to_trade never raises on malformed price data — it degrades to 0.0.

    Generalises the single-example coverage implied by its try/except into a
    property over the space of malformed ``price`` shapes it is meant to
    tolerate.
    """
    record = {
        "id": "1",
        "paging_token": "1",
        "ledger_close_time": datetime(2024, 1, 1).isoformat(),
        "base_account": "G" + "A" * 55,
        "counter_account": "G" + "B" * 55,
        "base_asset_code": "USDC",
        "base_asset_issuer": "G" + "C" * 55,
        "counter_asset_code": None,
        "counter_asset_issuer": None,
        "base_amount": 100.0,
        "counter_amount": 50.0,
        "price": price_raw,
    }

    trade = _amm_record_to_trade(record)
    assert trade.price == 0.0
