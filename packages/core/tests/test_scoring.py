from datetime import datetime, timedelta, timezone

import pytest

from detection import scoring
from detection.scoring import (
    MIN_BENFORD_SAMPLE,
    benford_report,
    score_wallet,
    trades_to_frame,
    wallets_in,
)
from ingestion.data_models import Asset, Trade

XLM = Asset(code="XLM")
USDC = Asset(code="USDC", issuer="GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")
T0 = datetime(2026, 6, 1, 2, 0, tzinfo=timezone.utc)


def _trade(i, base, counter, when, amount, seller=False):
    return Trade(
        id=str(i),
        ledger_close_time=when,
        base_account=base,
        counter_account=counter,
        base_asset=XLM,
        counter_asset=USDC,
        base_amount=amount,
        counter_amount=amount * 0.1,
        price=0.1,
        base_is_seller=seller,
    )


def _wash_pair(n=10):
    """Two wallets passing the same round lot back and forth, seconds apart."""
    return [
        _trade(i, "WA", "WB", T0 + timedelta(seconds=20 * i), 5000.0, seller=bool(i % 2))
        for i in range(n)
    ]


def _organic(n=40):
    amounts = [1872, 342, 91, 27840, 615, 1203, 187, 45, 9120, 2301]
    return [
        _trade(100 + i, "MAKER", f"T{i}", T0 + timedelta(hours=7 + i), float(amounts[i % 10] + i))
        for i in range(n)
    ]


def test_trades_to_frame_empty_has_expected_columns():
    df = trades_to_frame([])
    assert df.empty
    assert "base_account" in df.columns


def test_wash_pattern_scores_higher_than_organic():
    df = trades_to_frame(_wash_pair() + _organic())
    wash = score_wallet(df, "WA")
    organic = score_wallet(df, "MAKER")
    assert wash["score"] > organic["score"]
    assert wash["score"] >= 50
    assert wash["features"]["counterparty_concentration_ratio"] == pytest.approx(1.0)
    assert wash["features"]["round_trip_trade_frequency"] > 0


def test_heuristic_result_is_labelled():
    result = score_wallet(trades_to_frame(_wash_pair()), "WA")
    assert result["method"] == "heuristic"
    assert result["model"] is None
    assert result["ml_flag"] is False
    assert result["shap"] is None
    assert result["trade_count"] == 10
    assert result["as_of"] == T0 + timedelta(seconds=180)


def test_benford_not_used_below_minimum_sample():
    small = benford_report([5000.0] * (MIN_BENFORD_SAMPLE - 1))
    assert small["sufficient_sample"] is False
    assert small["non_conforming"] is False
    large = benford_report([5000.0] * MIN_BENFORD_SAMPLE)
    assert large["sufficient_sample"] is True
    assert large["non_conforming"] is True


def test_unknown_wallet_scores_zero():
    result = score_wallet(trades_to_frame(_organic()), "NOBODY")
    assert result["score"] == 0
    assert result["confidence"] == 0.0
    assert result["as_of"] is None


def test_wallets_in_excludes_pool_side():
    trades = _organic(3)
    pool = Trade(
        id="p1",
        ledger_close_time=T0,
        base_account="LP_USER",
        counter_account=None,
        base_asset=XLM,
        counter_asset=USDC,
        base_amount=10.0,
        counter_amount=1.0,
        price=0.1,
        base_is_seller=True,
        trade_type="liquidity_pool",
        liquidity_pool_id="pool1",
    )
    assert wallets_in(trades_to_frame(trades + [pool])) == ["LP_USER", "MAKER", "T0", "T1", "T2"]


def test_ml_path_is_labelled_with_model_identity():
    pytest.importorskip("sklearn")
    from detection.model import train_bundle

    X = [[1.0, 1.0, 0.5, 1.0, 0.5, 0.05]] * 10 + [[0.1, 0.0, 0.0, 0.1, 0.1, 0.005]] * 10
    y = [1] * 10 + [0] * 10
    bundle = train_bundle(X, y, trained_on="unit-test fixture")
    result = score_wallet(trades_to_frame(_wash_pair()), "WA", model_bundle=bundle)
    assert result["method"] == "ml"
    assert result["model"] == {"model_id": bundle["model_id"], "trained_on": "unit-test fixture"}
    assert set(result["shap"]) == set(scoring.MODEL_FEATURE_NAMES)
