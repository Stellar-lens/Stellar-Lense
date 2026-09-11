from fastapi.testclient import TestClient

from api import storage
from api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_score_for_known_wallet():
    pair = storage.known_pairs()[0]
    wallet = next(iter(storage.wallets_for_pair(pair)))

    response = client.get(f"/score/{wallet}/{pair}")
    assert response.status_code == 200

    body = response.json()
    assert body["wallet"] == wallet
    assert body["asset_pair"] == pair
    assert 0 <= body["score"] <= 100
    assert "benford_flag" in body
    assert "ml_flag" in body
    assert "confidence" in body


def test_get_score_unknown_pair_returns_404():
    # Valid Stellar account ID format, but the pair doesn't exist.
    response = client.get(
        "/score/GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/NOT/A/REAL/PAIR"
    )
    assert response.status_code == 404


def test_get_score_unknown_wallet_returns_404():
    pair = storage.known_pairs()[0]
    # Use a valid Base32 string (A-Z, 2-7) of length 56 starting with G
    response = client.get(f"/score/GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/{pair}")
    assert response.status_code == 404


def test_get_score_invalid_wallet_returns_400():
    pair = storage.known_pairs()[0]
    # Invalid length
    response = client.get(f"/score/GSHORT/{pair}")
    assert response.status_code == 400

    # Invalid starting character
    response = client.get(f"/score/HAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/{pair}")
    assert response.status_code == 400

    # Invalid characters (0 is not base32)
    response = client.get(f"/score/G0000000000000000000000000000000000000000000000000000000/{pair}")
    assert response.status_code == 400


def test_recent_alerts():
    response = client.get("/alerts/recent")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for alert in body:
        assert alert["score"] >= storage.ALERT_THRESHOLD
        assert "reason" in alert


def test_recent_alerts_respects_limit():
    response = client.get("/alerts/recent", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) <= 1


def test_asset_risk_ranking():
    response = client.get("/assets/risk-ranking")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == len(storage.known_pairs())
    # Ranking should be sorted descending by average score.
    scores = [r["average_score"] for r in body]
    assert scores == sorted(scores, reverse=True)


def test_pair_scores():
    pair = storage.known_pairs()[0]
    response = client.get(f"/assets/{pair}/scores")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(storage.wallets_for_pair(pair))
    scores = [r["score"] for r in body]
    assert scores == sorted(scores, reverse=True)
    for r in body:
        assert r["asset_pair"] == pair
        assert "features" in r
        assert "benford" in r


def test_pair_scores_unknown_pair_returns_404():
    response = client.get("/assets/NOT/A/REAL/PAIR/scores")
    assert response.status_code == 404


def test_pair_score_history():
    pair = storage.known_pairs()[0]
    response = client.get(f"/assets/{pair}/score-history")
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    # Chronological, oldest first.
    timestamps = [p["timestamp"] for p in body]
    assert timestamps == sorted(timestamps)
    for p in body:
        assert 0 <= p["average_score"] <= 100
        assert 0 <= p["max_score"] <= 100


def test_pair_score_history_unknown_pair_returns_404():
    response = client.get("/assets/NOT/A/REAL/PAIR/score-history")
    assert response.status_code == 404
