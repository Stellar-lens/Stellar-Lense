"""Per-wallet wash-trading risk scoring.

`score_wallet` is the single scoring entry point used by the product. It
always computes Benford's Law metrics and the trade-pattern features from
`detection.feature_engineering`, then derives a 0-100 score in one of two
ways, and says which in the result's ``method`` field:

* ``"heuristic"`` (default): a fixed, documented weighted sum of the
  features plus a capped Benford term. No training data involved.
* ``"ml"``: only when a model bundle is passed in (see `detection.model`).
  The bundle carries its own ``model_id`` and a ``trained_on`` description,
  which are echoed in the result so consumers can see what produced a score.

Benford statistics are only *used* (flag + score contribution) once a wallet
has at least `MIN_BENFORD_SAMPLE` trades; first-digit tests on a handful of
amounts are noise. The raw metrics are still reported either way.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import pandas as pd

from config.settings import settings
from detection.benford_engine import compute_benford_metrics
from detection.feature_engineering import (
    counterparty_concentration_ratio,
    intra_minute_clustering_coefficient,
    off_hours_activity_ratio,
    round_trip_trade_frequency,
    self_matching_rate,
    volume_to_unique_counterparty_ratio,
)
from ingestion.data_models import Trade

# Weights for the heuristic score. Each feature is a ratio in [0, 1], so the
# features alone contribute at most 85 points; Benford adds at most 15.
HEURISTIC_WEIGHTS: dict[str, float] = {
    "counterparty_concentration_ratio": 25.0,
    "round_trip_trade_frequency": 25.0,
    "self_matching_rate": 20.0,
    "intra_minute_clustering_coefficient": 10.0,
    "off_hours_activity_ratio": 5.0,
}
BENFORD_WEIGHT = 500.0
BENFORD_MAX_CONTRIBUTION = 15.0
MIN_BENFORD_SAMPLE = 30

# Feature order for the optional ML model. Changing it invalidates trained
# models; `detection.model` stores this list in each bundle and checks it.
MODEL_FEATURE_NAMES: list[str] = [*HEURISTIC_WEIGHTS, "benford_mad"]

TRADE_COLUMNS = [
    "id",
    "ledger_close_time",
    "base_account",
    "counter_account",
    "base_asset",
    "counter_asset",
    "base_amount",
    "counter_amount",
    "price",
    "base_is_seller",
]


def trades_to_frame(trades: Iterable[Trade]) -> pd.DataFrame:
    """Build the DataFrame shape the feature functions expect from `Trade`s."""
    rows = [t.model_dump() for t in trades]
    if not rows:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    df = pd.DataFrame(rows)
    df["ledger_close_time"] = pd.to_datetime(df["ledger_close_time"], utc=True)
    return df


def _wallet_trades(trades: pd.DataFrame, wallet: str) -> pd.DataFrame:
    if trades.empty:
        return trades
    mask = (trades["base_account"] == wallet) | (trades["counter_account"] == wallet)
    return trades.loc[mask]


def wallet_features(trades: pd.DataFrame, wallet: str) -> dict[str, float]:
    """The heuristic feature set for `wallet`, computed over its own trades."""
    own = _wallet_trades(trades, wallet)
    if own.empty:
        return {name: 0.0 for name in [*HEURISTIC_WEIGHTS, "volume_to_unique_counterparty_ratio"]}
    return {
        "counterparty_concentration_ratio": counterparty_concentration_ratio(own, wallet),
        "round_trip_trade_frequency": round_trip_trade_frequency(own, wallet),
        "self_matching_rate": self_matching_rate(own),
        "intra_minute_clustering_coefficient": intra_minute_clustering_coefficient(own),
        "off_hours_activity_ratio": off_hours_activity_ratio(own),
        "volume_to_unique_counterparty_ratio": volume_to_unique_counterparty_ratio(own, wallet),
    }


def benford_report(amounts: list[float]) -> dict[str, Any]:
    """Benford metrics plus whether there were enough samples to judge."""
    metrics = compute_benford_metrics(amounts)
    sufficient = metrics["sample_size"] >= MIN_BENFORD_SAMPLE
    return {
        "sample_size": metrics["sample_size"],
        "chi_square": float(metrics["chi_square"]),
        "chi_square_pvalue": float(metrics["chi_square_pvalue"]),
        "mad": float(metrics["mad"]),
        "z_scores": {int(d): float(z) for d, z in metrics["z_scores"].items()},
        "sufficient_sample": sufficient,
        "non_conforming": bool(sufficient and metrics["mad"] > settings.benford_mad_threshold),
    }


def heuristic_score(features: dict[str, float], benford: dict[str, Any]) -> int:
    raw = sum(weight * features[name] for name, weight in HEURISTIC_WEIGHTS.items())
    if benford["sufficient_sample"]:
        raw += min(benford["mad"] * BENFORD_WEIGHT, BENFORD_MAX_CONTRIBUTION)
    return int(round(min(max(raw, 0.0), 100.0)))


def model_feature_vector(features: dict[str, float], benford: dict[str, Any]) -> list[float]:
    values = {**features, "benford_mad": benford["mad"]}
    return [float(values[name]) for name in MODEL_FEATURE_NAMES]


def score_wallet(
    trades: pd.DataFrame,
    wallet: str,
    model_bundle: dict[str, Any] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Score `wallet` from `trades` (a `trades_to_frame`-shaped DataFrame).

    Returns ``wallet, score, method, model, benford_flag, ml_flag,
    confidence, trade_count, as_of, features, benford, shap``.
    """
    own = _wallet_trades(trades, wallet)
    features = wallet_features(trades, wallet)
    benford = benford_report(own["base_amount"].astype(float).tolist() if not own.empty else [])

    shap_values: dict[str, float] | None = None
    if model_bundle is not None:
        from detection.model import predict_with_explanation

        probability, shap_values = predict_with_explanation(
            model_bundle, model_feature_vector(features, benford)
        )
        score = int(round(probability * 100))
        method = "ml"
        model_info = {
            "model_id": model_bundle["model_id"],
            "trained_on": model_bundle["trained_on"],
        }
    else:
        score = heuristic_score(features, benford)
        method = "heuristic"
        model_info = None

    trade_count = len(own)
    if as_of is None and trade_count:
        as_of = own["ledger_close_time"].max().to_pydatetime()

    return {
        "wallet": wallet,
        "score": score,
        "method": method,
        "model": model_info,
        "benford_flag": benford["non_conforming"],
        "ml_flag": method == "ml" and score >= settings.risk_score_threshold,
        # Confidence grows with evidence: 40 at one trade, capped at 100.
        "confidence": round(min(100.0, 40.0 + trade_count), 1) if trade_count else 0.0,
        "trade_count": trade_count,
        "as_of": as_of,
        "features": features,
        "benford": benford,
        "shap": shap_values,
    }


def wallets_in(trades: pd.DataFrame) -> list[str]:
    """Every wallet appearing on either side of `trades` (pool sides excluded)."""
    if trades.empty:
        return []
    accounts = pd.concat([trades["base_account"], trades["counter_account"]]).dropna()
    return sorted(a for a in accounts.unique() if a)
