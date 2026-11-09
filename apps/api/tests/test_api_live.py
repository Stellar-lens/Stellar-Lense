"""API behaviour in live mode: reads the pipeline's SQLite store."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from detection.scoring import trades_to_frame
from ingestion.data_models import Asset, Trade
from pipeline.jobs import Pair, PairConfig, score
from pipeline.store import Store

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
XLM = Asset(code="XLM")
USDC = Asset(code="USDC", issuer="GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")
PAIR = Pair("XLM", "USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")
WASH_A = "G" + "A" * 55
WASH_B = "G" + "B" * 55
MAKER = "G" + "C" * 55

client = TestClient(app)


def _trades():
    out = []
    for k in range(20):
        out.append(
            Trade(
                id=f"w{k}",
                ledger_close_time=NOW - timedelta(minutes=100 - k * 2),
                base_account=WASH_A,
                counter_account=WASH_B,
                base_asset=XLM,
                counter_asset=USDC,
                base_amount=5000.0,
                counter_amount=500.0,
                price=0.1,
                base_is_seller=k % 2 == 0,
            )
        )
    for k in range(10):
        out.append(
            Trade(
                id=f"m{k}",
                ledger_close_time=NOW - timedelta(minutes=300 - k * 13),
                base_account=MAKER,
                counter_account="G" + chr(ord("D") + k) * 55,
                base_asset=XLM,
                counter_asset=USDC,
                base_amount=100.0 + 37 * k,
                counter_amount=10.0,
                price=0.1,
                base_is_seller=k % 3 == 0,
            )
        )
    return out


@pytest.fixture
def live_db(tmp_path, monkeypatch):
    db = tmp_path / "live.db"
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("DB_PATH", str(db))
    return db


def _populate(db):
    store = Store(db)
    store.insert_trades(PAIR.id, trades_to_frame(_trades()))
    store.save_market(
        PAIR.id,
        {
            "price": 0.1,
            "change_24h_pct": -2.5,
            "base_volume_24h": 1234.0,
            "counter_volume_24h": 123.4,
            "trade_count_24h": 30,
            "window_start": NOW - timedelta(hours=24),
            "window_end": NOW,
        },
    )
    score(store, PairConfig("https://horizon.test", "mainnet", [PAIR]), now=NOW)


def test_no_database_yet_returns_503(live_db):
    response = client.get("/assets/risk-ranking")
    assert response.status_code == 503
    assert "pipeline" in response.json()["detail"]


def test_live_endpoints_serve_stored_scores(live_db):
    _populate(live_db)

    meta = client.get("/meta").json()
    assert meta["mode"] == "live"
    assert meta["data_as_of"].startswith((NOW - timedelta(minutes=62)).strftime("%Y-%m-%dT%H:%M"))
    assert meta["scoring"]["method"] == "heuristic"
    assert meta["notice"] is None

    ranking = client.get("/assets/risk-ranking").json()
    assert [r["asset_pair"] for r in ranking] == [PAIR.id]
    assert ranking[0]["total_wallets"] == 3  # takers trade once, below MIN_TRADES

    scores = client.get(f"/assets/{PAIR.id}/scores").json()
    assert scores[0]["wallet"] in (WASH_A, WASH_B)
    assert all(s["method"] == "heuristic" for s in scores)

    one = client.get(f"/score/{WASH_A}/{PAIR.id}").json()
    assert one["trade_count"] == 20

    history = client.get(f"/assets/{PAIR.id}/score-history").json()
    assert len(history) == 1

    market = client.get(f"/market/{PAIR.id}").json()
    assert market["price"] == 0.1 and market["trade_count_24h"] == 30


def test_live_unknown_pair_and_wallet(live_db):
    _populate(live_db)
    assert client.get("/assets/XLM/NOPE:GX/scores").status_code == 404
    assert client.get(f"/score/{'G' + 'Z' * 55}/{PAIR.id}").status_code == 404
    assert client.get("/market/XLM/NOPE:GX").status_code == 404
