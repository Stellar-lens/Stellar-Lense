from datetime import datetime, timedelta, timezone

import pytest

from ingestion.historical_loader import load_historical_trades
from ingestion.market_data import load_market_snapshot, snapshot_from_candles
from pipeline.jobs import Pair, PairConfig, ingest, load_pairs, score
from pipeline.store import Store
from tests.fake_horizon import USDC_ISSUER, FakeHorizon, trade_record, wash_and_organic

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
USDC = f"USDC:{USDC_ISSUER}"
PAIR = Pair("XLM", USDC)
CONFIG = PairConfig(horizon_url="https://horizon.test", network="mainnet", pairs=[PAIR])


def _horizon(records=None):
    return FakeHorizon(records if records is not None else wash_and_organic(NOW))


def test_loader_stops_at_since_and_respects_max_records():
    fake = _horizon()
    newest_first = fake.records
    since = datetime.fromisoformat(newest_first[10]["ledger_close_time"].replace("Z", "+00:00"))
    df = load_historical_trades(
        "XLM", USDC, since=since, horizon_url="https://horizon.test", client=fake.client()
    )
    assert len(df) == 10  # strictly newer than `since`
    capped = load_historical_trades(
        "XLM", USDC, since=NOW - timedelta(days=1), max_records=7,
        horizon_url="https://horizon.test", client=fake.client(),
    )
    assert len(capped) == 7


def test_loader_sends_asset_filters():
    fake = _horizon()
    load_historical_trades("XLM", USDC, max_records=1, horizon_url="https://horizon.test", client=fake.client())
    assert "base_asset_type=native" in fake.requests[0]
    assert f"counter_asset_issuer={USDC_ISSUER}" in fake.requests[0]


def test_market_snapshot_from_candles():
    start, end = NOW - timedelta(hours=24), NOW
    snap = snapshot_from_candles(
        "XLM",
        USDC,
        [
            {"open": "0.10", "close": "0.11", "base_volume": "100", "counter_volume": "10.5", "trade_count": "3"},
            {"open": "0.11", "close": "0.12", "base_volume": "50", "counter_volume": "6", "trade_count": "2"},
        ],
        start,
        end,
    )
    assert snap.price == 0.12
    assert snap.change_24h_pct == pytest.approx(20.0)
    assert snap.base_volume_24h == 150
    assert snap.trade_count_24h == 5
    empty = snapshot_from_candles("XLM", USDC, [], start, end)
    assert empty.price is None and empty.trade_count_24h == 0


def test_market_snapshot_from_horizon():
    snap = load_market_snapshot("XLM", USDC, now=NOW, horizon_url="https://horizon.test", client=_horizon().client())
    assert snap.trade_count_24h == 60
    assert snap.price is not None


def test_ingest_then_score_end_to_end(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    fake = _horizon()
    summary = ingest(store, CONFIG, client=fake.client(), now=NOW)
    assert summary[PAIR.id] == {"fetched": 60, "inserted": 60}
    assert store.market(PAIR.id)[0]["trade_count_24h"] == 60

    # A second run only fetches trades newer than what's stored: none.
    again = ingest(store, CONFIG, client=fake.client(), now=NOW)
    assert again[PAIR.id] == {"fetched": 0, "inserted": 0}

    result = score(store, CONFIG, now=NOW)
    run = store.latest_score_run()
    assert run["id"] == result["run_id"]
    assert run["method"] == "heuristic"
    assert run["data_as_of"] == max(
        datetime.fromisoformat(r["ledger_close_time"].replace("Z", "+00:00")) for r in fake.records
    )
    scores = {s["wallet"]: s for s in store.scores(run["id"], PAIR.id)}
    # Takers trade once each, below MIN_TRADES, so they aren't scored.
    assert set(scores) == {"GWASHA", "GWASHB", "GMAKER"}
    assert scores["GWASHA"]["score"] > scores["GMAKER"]["score"]
    assert scores["GWASHA"]["method"] == "heuristic"
    assert store.pair_history(PAIR.id)[-1]["max_score"] == scores["GWASHA"]["score"]


def test_ingest_records_errors_per_pair_and_continues(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    bad = Pair("XLM", "NOPE:GBAD")
    config = PairConfig("https://horizon.test", "mainnet", [bad, PAIR])

    class Boom(FakeHorizon):
        def handle(self, request):
            if "NOPE" in str(request.url):
                raise RuntimeError("horizon down")
            return super().handle(request)

    summary = ingest(store, config, client=Boom(wash_and_organic(NOW)).client(), now=NOW)
    assert "error" in summary[bad.id]
    assert summary[PAIR.id]["inserted"] == 60


def test_pool_trades_are_stored_and_reloaded(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    records = [trade_record(1, NOW - timedelta(minutes=5), "GLP", None, 10.0)]
    ingest(store, CONFIG, client=FakeHorizon(records).client(), now=NOW)
    df = store.trades_for_pair(PAIR.id)
    assert df.iloc[0]["counter_account"] is None
    assert df.iloc[0]["trade_type"] == "liquidity_pool"


def test_default_pair_file_is_valid():
    config = load_pairs()
    assert config.network == "mainnet"
    assert 10 <= len(config.pairs) <= 20
    assert len({p.id for p in config.pairs}) == len(config.pairs)


def test_dust_trade_with_zero_amount_is_skipped_not_fatal(tmp_path):
    records = wash_and_organic(NOW)
    dust = trade_record(999, NOW - timedelta(minutes=1), "GDUST", "GOTHER", 1.0)
    dust["counter_amount"] = "0.0000000"
    df = load_historical_trades(
        "XLM", USDC, since=NOW - timedelta(days=1),
        horizon_url="https://horizon.test", client=FakeHorizon(records + [dust]).client(),
    )
    assert len(df) == 60
    assert df.attrs["skipped"] == 1

    store = Store(tmp_path / "db.sqlite")
    summary = ingest(store, CONFIG, client=FakeHorizon(records + [dust]).client(), now=NOW)
    assert summary[PAIR.id]["inserted"] == 60
