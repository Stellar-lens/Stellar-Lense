"""Shared Hypothesis strategies for transaction-normalization property tests.

These strategies encode the *contract* for a valid Stellar trade record so
that every property test — ingestion converters, the Avro codec, the Kafka
producer's canonical pair-id builder, and the per-pair metrics label
normaliser — draws from the same definition of "a valid asset code", "a valid
issuer", and "a valid trade". Centralising them here means the modules can't
silently drift apart the way independent hand-picked example tests can.

See ``docs/ingestion.md`` ("Transaction normalization contract") for the
invariants these strategies are built to exercise.
"""

from datetime import UTC, datetime

from hypothesis import strategies as st

from ingestion.data_models import Asset, Trade

# Stellar asset codes: 1-12 uppercase alphanumeric characters.
# Mirrors ingestion/kafka_producer.py::_ASSET_CODE_RE.
_CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

asset_codes = st.text(alphabet=_CODE_ALPHABET, min_size=1, max_size=12)

# Stellar account/issuer IDs: "G" + 55 uppercase alphanumeric characters.
# Mirrors ingestion/kafka_producer.py::_ISSUER_RE.
stellar_ids = st.text(alphabet=_CODE_ALPHABET, min_size=55, max_size=55).map(
    lambda tail: "G" + tail
)

# An asset's issuer field: None (native/XLM) or a valid issuer account id.
issuers = st.one_of(st.none(), stellar_ids)

# Trade amounts/prices: finite, positive, within a realistic magnitude range.
# IEEE-754 doubles round-trip exactly through the Avro "double" wire type, so
# no tolerance is needed when asserting equality after encode/decode.
finite_amounts = st.floats(min_value=1e-7, max_value=1e12, allow_nan=False, allow_infinity=False)
finite_prices = st.floats(min_value=1e-9, max_value=1e6, allow_nan=False, allow_infinity=False)

# Trade ids / account ids used where only "some non-empty string" matters.
non_empty_text = st.text(min_size=1, max_size=64).filter(lambda s: s.strip() != "")

# ledger_close_time is wire-encoded as Avro `timestamp-millis`, so anything
# with sub-millisecond precision gets truncated on the way through. Aligning
# the generated datetime to whole milliseconds up front lets round-trip tests
# assert exact equality instead of a truncation tolerance.
ms_aligned_datetimes = st.datetimes(
    min_value=datetime(2015, 1, 1),
    max_value=datetime(2035, 1, 1),
).map(lambda dt: dt.replace(microsecond=(dt.microsecond // 1000) * 1000, tzinfo=UTC))


@st.composite
def assets(draw) -> Asset:
    """A syntactically valid Stellar :class:`Asset` (code + optional issuer)."""
    return Asset(code=draw(asset_codes), issuer=draw(issuers))


@st.composite
def trades(draw) -> Trade:
    """A syntactically valid :class:`Trade`, ready for normalization round-tripping."""
    return Trade(
        trade_id=draw(non_empty_text),
        ledger_close_time=draw(ms_aligned_datetimes),
        base_account=draw(stellar_ids),
        counter_account=draw(stellar_ids),
        base_asset=draw(assets()),
        counter_asset=draw(assets()),
        base_amount=draw(finite_amounts),
        counter_amount=draw(finite_amounts),
        price=draw(finite_prices),
    )


# ---------------------------------------------------------------------------
# Invalid inputs — for asserting that normalizers *reject* malformed data
# rather than silently accepting or corrupting it.
# ---------------------------------------------------------------------------

invalid_asset_codes = st.one_of(
    st.just(""),  # empty
    st.text(alphabet=_CODE_ALPHABET, min_size=13, max_size=20),  # too long
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12),  # lowercase
    st.text(alphabet=" !@#$%^&*()", min_size=1, max_size=5),  # punctuation/whitespace
)

invalid_issuers = st.one_of(
    st.just(""),
    st.text(alphabet=_CODE_ALPHABET, min_size=54, max_size=54).map(lambda t: "G" + t),  # 1 short
    st.text(alphabet=_CODE_ALPHABET, min_size=56, max_size=56).map(lambda t: "G" + t),  # 1 long
    st.text(alphabet=_CODE_ALPHABET, min_size=55, max_size=55).map(lambda t: "X" + t),  # bad prefix
)


# ---------------------------------------------------------------------------
# Raw source records — the untyped dicts that ingestion converters normalize
# into a Trade. Shapes mirror ingestion/horizon_streamer.py::_to_trade and
# ingestion/amm_pool_loader.py::_amm_record_to_trade.
# ---------------------------------------------------------------------------


@st.composite
def raw_native_asset_fields(draw, *, prefix: str) -> dict:
    """Raw ``{prefix}_asset_code``/``{prefix}_asset_issuer`` fields for native XLM.

    Horizon represents the native asset with an empty/absent code and no
    issuer — this is the shape both ``_to_trade`` and ``_amm_record_to_trade``
    are expected to normalize to ``Asset(code="XLM", issuer=None)``.
    """
    code = draw(st.one_of(st.none(), st.just("")))
    return {f"{prefix}_asset_code": code, f"{prefix}_asset_issuer": None}


@st.composite
def raw_issued_asset_fields(draw, *, prefix: str) -> dict:
    """Raw ``{prefix}_asset_code``/``{prefix}_asset_issuer`` fields for a non-native asset."""
    return {
        f"{prefix}_asset_code": draw(asset_codes),
        f"{prefix}_asset_issuer": draw(stellar_ids),
    }


@st.composite
def raw_horizon_trade_records(draw) -> dict:
    """A raw dict shaped like a Stellar Horizon SSE trade event.

    Suitable input for ``ingestion.horizon_streamer._to_trade``.
    """
    base_fields = draw(
        st.one_of(raw_native_asset_fields(prefix="base"), raw_issued_asset_fields(prefix="base"))
    )
    counter_fields = draw(
        st.one_of(
            raw_native_asset_fields(prefix="counter"), raw_issued_asset_fields(prefix="counter")
        )
    )
    return {
        "id": draw(non_empty_text),
        "ledger_close_time": draw(ms_aligned_datetimes).isoformat(),
        "base_account": draw(stellar_ids),
        "counter_account": draw(stellar_ids),
        "base_amount": draw(finite_amounts),
        "counter_amount": draw(finite_amounts),
        "price": {
            "n": draw(st.integers(min_value=1, max_value=10_000)),
            "d": draw(st.integers(min_value=1, max_value=10_000)),
        },
        **base_fields,
        **counter_fields,
    }


@st.composite
def raw_amm_pool_records(draw) -> dict:
    """A raw dict shaped like a Horizon liquidity-pool trade effect.

    Suitable input for ``ingestion.amm_pool_loader._amm_record_to_trade``.
    """
    base_fields = draw(
        st.one_of(raw_native_asset_fields(prefix="base"), raw_issued_asset_fields(prefix="base"))
    )
    counter_fields = draw(
        st.one_of(
            raw_native_asset_fields(prefix="counter"), raw_issued_asset_fields(prefix="counter")
        )
    )
    return {
        "id": draw(non_empty_text),
        "paging_token": draw(non_empty_text),
        "ledger_close_time": draw(ms_aligned_datetimes).isoformat(),
        "base_account": draw(stellar_ids),
        "counter_account": draw(stellar_ids),
        "base_amount": draw(finite_amounts),
        "counter_amount": draw(finite_amounts),
        "price": {
            "n": draw(st.integers(min_value=1, max_value=10_000)),
            "d": draw(st.integers(min_value=1, max_value=10_000)),
        },
        **base_fields,
        **counter_fields,
    }
