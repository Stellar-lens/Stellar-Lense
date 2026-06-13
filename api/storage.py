"""In-memory data store backing the LedgerLens demo API.

This stands in for the production data layer (populated by the ingestion
pipeline and Soroban contract reads). It seeds a small set of trades —
including a synthetic wash-trading pattern — so the API endpoints have
realistic data to serve.
"""

from datetime import datetime, timedelta

from detection.model_inference import score_wallet
from ingestion.data_models import Asset, Trade

# Risk score at or above this value generates an alert.
ALERT_THRESHOLD = 50

XLM = Asset(code="XLM")
USDC = Asset(code="USDC", issuer="GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")
YBX = Asset(code="YBX", issuer="GBYBX0000000000000000000000000000000000000000000000000")


def _trade(trade_id, base_account, counter_account, when, base_asset, counter_asset, amount, price, base_is_seller=False):
    return Trade(
        id=trade_id,
        ledger_close_time=when,
        base_account=base_account,
        counter_account=counter_account,
        base_asset=base_asset,
        counter_asset=counter_asset,
        base_amount=amount,
        counter_amount=amount * price,
        price=price,
        base_is_seller=base_is_seller,
    )


_T0 = datetime(2026, 6, 1, 0, 0, 0)

# Synthetic wash-trading cluster: two wallets repeatedly trade fixed-size
# round-number lots back and forth on the XLM/USDC pair.
_WASH_TRADES = [
    _trade("wash-1", "GWASHA000000000000000000000000000000000000000000000000", "GWASHB000000000000000000000000000000000000000000000000", _T0, XLM, USDC, 5000, 0.1, base_is_seller=False),
    _trade("wash-2", "GWASHA000000000000000000000000000000000000000000000000", "GWASHB000000000000000000000000000000000000000000000000", _T0 + timedelta(seconds=20), XLM, USDC, 5000, 0.1, base_is_seller=True),
    _trade("wash-3", "GWASHA000000000000000000000000000000000000000000000000", "GWASHB000000000000000000000000000000000000000000000000", _T0 + timedelta(minutes=2), XLM, USDC, 5000, 0.1, base_is_seller=False),
    _trade("wash-4", "GWASHA000000000000000000000000000000000000000000000000", "GWASHB000000000000000000000000000000000000000000000000", _T0 + timedelta(minutes=2, seconds=15), XLM, USDC, 5000, 0.1, base_is_seller=True),
    _trade("wash-5", "GWASHA000000000000000000000000000000000000000000000000", "GWASHB000000000000000000000000000000000000000000000000", _T0 + timedelta(minutes=4), XLM, USDC, 5000, 0.1, base_is_seller=False),
]

# Synthetic organic activity: a market maker trading varied amounts with
# many different counterparties on the XLM/USDC pair.
_CLEAN_TRADES = [
    _trade("clean-1", "GMAKER0000000000000000000000000000000000000000000000000", "GTRADER100000000000000000000000000000000000000000000000", _T0 + timedelta(hours=1), XLM, USDC, 1872, 0.0998),
    _trade("clean-2", "GMAKER0000000000000000000000000000000000000000000000000", "GTRADER200000000000000000000000000000000000000000000000", _T0 + timedelta(hours=2), XLM, USDC, 342, 0.1003),
    _trade("clean-3", "GMAKER0000000000000000000000000000000000000000000000000", "GTRADER300000000000000000000000000000000000000000000000", _T0 + timedelta(hours=5), XLM, USDC, 91, 0.1001),
    _trade("clean-4", "GMAKER0000000000000000000000000000000000000000000000000", "GTRADER400000000000000000000000000000000000000000000000", _T0 + timedelta(hours=9), XLM, USDC, 27840, 0.0997),
    _trade("clean-5", "GMAKER0000000000000000000000000000000000000000000000000", "GTRADER500000000000000000000000000000000000000000000000", _T0 + timedelta(hours=14), XLM, USDC, 615, 0.1002),
]

# A second, less severe wash pattern on a smaller asset pair (XLM/YBX).
_MINOR_WASH_TRADES = [
    _trade("ybx-1", "GWASHC000000000000000000000000000000000000000000000000", "GWASHD000000000000000000000000000000000000000000000000", _T0, XLM, YBX, 1000, 2.5, base_is_seller=False),
    _trade("ybx-2", "GWASHC000000000000000000000000000000000000000000000000", "GWASHD000000000000000000000000000000000000000000000000", _T0 + timedelta(minutes=1), XLM, YBX, 1000, 2.5, base_is_seller=True),
]

ALL_TRADES: list[Trade] = _WASH_TRADES + _CLEAN_TRADES + _MINOR_WASH_TRADES


def _pair_id(trade: Trade) -> str:
    return trade.pair.identifier


def trades_for_pair(pair_id: str) -> list[Trade]:
    return [t for t in ALL_TRADES if _pair_id(t) == pair_id]


def known_pairs() -> list[str]:
    seen = []
    for t in ALL_TRADES:
        pid = _pair_id(t)
        if pid not in seen:
            seen.append(pid)
    return seen


def wallets_for_pair(pair_id: str) -> set[str]:
    wallets: set[str] = set()
    for t in trades_for_pair(pair_id):
        wallets.add(t.base_account)
        wallets.add(t.counter_account)
    return wallets


def compute_risk_score(wallet: str, pair_id: str) -> dict:
    """Score `wallet` using only trades on `pair_id`."""
    trades = trades_for_pair(pair_id)
    result = score_wallet(trades, wallet)
    result["asset_pair"] = pair_id
    result["timestamp"] = ALL_TRADES[-1].ledger_close_time
    return result


def all_scores() -> list[dict]:
    """Risk scores for every wallet/asset-pair combination present in the data."""
    scores = []
    for pair_id in known_pairs():
        for wallet in wallets_for_pair(pair_id):
            scores.append(compute_risk_score(wallet, pair_id))
    return scores


def recent_alerts(limit: int = 20) -> list[dict]:
    """Wallet/asset-pair combinations whose risk score meets ALERT_THRESHOLD."""
    flagged = [s for s in all_scores() if s["score"] >= ALERT_THRESHOLD]
    flagged.sort(key=lambda s: s["score"], reverse=True)
    alerts = []
    for s in flagged[:limit]:
        reasons = []
        if s["benford_flag"]:
            reasons.append("non-conforming digit distribution")
        if s["components"]["features"]["round_trip_trade_frequency"] > 0:
            reasons.append("round-trip trading detected")
        if s["components"]["features"]["counterparty_concentration_ratio"] > 0.8:
            reasons.append("high counterparty concentration")
        reason = "; ".join(reasons) or "elevated risk score"
        alerts.append(
            {
                "id": f"{s['asset_pair']}:{s['wallet']}",
                "wallet": s["wallet"],
                "asset_pair": s["asset_pair"],
                "score": s["score"],
                "reason": reason,
                "timestamp": s["timestamp"],
            }
        )
    return alerts


def asset_risk_ranking() -> list[dict]:
    """Aggregate risk ranking for each asset pair."""
    rankings = []
    for pair_id in known_pairs():
        scores = [compute_risk_score(w, pair_id) for w in wallets_for_pair(pair_id)]
        if not scores:
            continue
        values = [s["score"] for s in scores]
        rankings.append(
            {
                "asset_pair": pair_id,
                "average_score": round(sum(values) / len(values), 2),
                "max_score": max(values),
                "flagged_wallets": sum(1 for v in values if v >= ALERT_THRESHOLD),
                "total_wallets": len(values),
            }
        )
    rankings.sort(key=lambda r: r["average_score"], reverse=True)
    return rankings
