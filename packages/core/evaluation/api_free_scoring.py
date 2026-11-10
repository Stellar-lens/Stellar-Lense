"""Rebuild the committed trades CSV into scorer input and score each labelled wallet."""

from __future__ import annotations

import pandas as pd

from detection.scoring import score_wallet

# Same as apps/api's alert threshold (apps/api/api/alerts.py).
ALERT_THRESHOLD = 50


def _asset(symbol: str) -> dict:
    code, _, issuer = symbol.partition(":")
    return {"code": code, "issuer": issuer or None}


def to_scoring_frame(trades: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    df["ledger_close_time"] = pd.to_datetime(df["ledger_close_time"], utc=True, format="ISO8601")
    df["base_asset"] = df["base_asset"].map(_asset)
    df["counter_asset"] = df["counter_asset"].map(_asset)
    df["base_is_seller"] = df["base_is_seller"].astype(bool)
    df["counter_account"] = df["counter_account"].astype(object).where(df["counter_account"].notna(), None)
    return df


def score_labelled(labelled: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    frame = to_scoring_frame(trades)
    by_pair = {pair: g for pair, g in frame.groupby("pair")}
    scores = []
    for row in labelled.itertuples():
        pair_trades = by_pair.get(row.pair, frame.iloc[0:0])
        scores.append(score_wallet(pair_trades, row.wallet)["score"])
    return labelled.assign(score=scores)
