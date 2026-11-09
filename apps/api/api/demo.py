"""Demo backend: 12 hard-coded synthetic trades, scored on request.

Only used when DEMO_MODE=1 (see api/storage.py). Every response made from
it is labelled demo by /meta, and apps/web shows a demo banner. None of
these wallets or trades exist on the Stellar network.
"""

from datetime import datetime, timedelta, timezone

from detection.scoring import score_wallet as _core_score_wallet
from detection.scoring import trades_to_frame
from ingestion.data_models import Asset, Trade

from api.alerts import ALERT_THRESHOLD, to_alert

XLM = Asset(code="XLM")
USDC = Asset(code="USDC", issuer="GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")
YBX = Asset(code="YBX", issuer="GBYBXAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")


def score_wallet(trades: list[Trade], wallet: str) -> dict:
    """Score `wallet` with packages/core's engine over the given trades."""
    return _core_score_wallet(trades_to_frame(trades), wallet)


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


_T0 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)

# Synthetic wash-trading cluster: two wallets repeatedly trade fixed-size
# round-number lots back and forth on the XLM/USDC pair.
_WASH_TRADES = [
    _trade("wash-1", "GWASHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GWASHBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0, XLM, USDC, 5000, 0.1, base_is_seller=False),
    _trade("wash-2", "GWASHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GWASHBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(seconds=20), XLM, USDC, 5000, 0.1, base_is_seller=True),
    _trade("wash-3", "GWASHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GWASHBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(minutes=2), XLM, USDC, 5000, 0.1, base_is_seller=False),
    _trade("wash-4", "GWASHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GWASHBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(minutes=2, seconds=15), XLM, USDC, 5000, 0.1, base_is_seller=True),
    _trade("wash-5", "GWASHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GWASHBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(minutes=4), XLM, USDC, 5000, 0.1, base_is_seller=False),
]

# Synthetic organic activity: a market maker trading varied amounts with
# many different counterparties on the XLM/USDC pair.
_CLEAN_TRADES = [
    _trade("clean-1", "GMAKERAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GTRADERAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(hours=1), XLM, USDC, 1872, 0.0998),
    _trade("clean-2", "GMAKERAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GTRADERBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(hours=2), XLM, USDC, 342, 0.1003),
    _trade("clean-3", "GMAKERAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GTRADERCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(hours=5), XLM, USDC, 91, 0.1001),
    _trade("clean-4", "GMAKERAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GTRADERDAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(hours=9), XLM, USDC, 27840, 0.0997),
    _trade("clean-5", "GMAKERAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GTRADEREAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(hours=14), XLM, USDC, 615, 0.1002),
]

# A second, less severe wash pattern on a smaller asset pair (XLM/YBX).
_MINOR_WASH_TRADES = [
    _trade("ybx-1", "GWASHCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GWASHDAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0, XLM, YBX, 1000, 2.5, base_is_seller=False),
    _trade("ybx-2", "GWASHCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "GWASHDAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", _T0 + timedelta(minutes=1), XLM, YBX, 1000, 2.5, base_is_seller=True),
]

ALL_TRADES: list[Trade] = _WASH_TRADES + _CLEAN_TRADES + _MINOR_WASH_TRADES


def _pair_id(trade: Trade) -> str:
    return trade.asset_pair


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
    return [to_alert(s) for s in flagged[:limit]]


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


def pair_score_history(pair_id: str) -> list[dict]:
    """Aggregate score recomputed at each distinct trade time in the seed
    data. The demo has no stored runs, so this is a simulated history."""
    trades = trades_for_pair(pair_id)
    if not trades:
        return []

    cutoffs = sorted({t.ledger_close_time for t in trades})
    history = []
    for cutoff in cutoffs:
        window = [t for t in trades if t.ledger_close_time <= cutoff]
        wallets = {w for t in window for w in (t.base_account, t.counter_account)}
        scores = [score_wallet(window, w)["score"] for w in wallets]
        if not scores:
            continue
        history.append(
            {
                "timestamp": cutoff,
                "average_score": round(sum(scores) / len(scores), 2),
                "max_score": max(scores),
            }
        )
    return history


def meta() -> dict:
    return {
        "mode": "demo",
        "network": None,
        "data_as_of": max(t.ledger_close_time for t in ALL_TRADES),
        "scored_at": None,
        "last_ingest": None,
        "pairs_tracked": len(known_pairs()),
        "scoring": {"method": "heuristic", "model": None, "min_trades": 1},
        "notice": "Demo mode: 12 hard-coded synthetic trades, not Stellar network data.",
    }


def market() -> list[dict]:
    """The demo has no market data; it never invents prices."""
    return []


def pair_scores(pair_id: str) -> list[dict] | None:
    if pair_id not in known_pairs():
        return None
    results = [compute_risk_score(w, pair_id) for w in wallets_for_pair(pair_id)]
    return sorted(results, key=lambda r: r["score"], reverse=True)


def wallet_score(wallet: str, pair_id: str) -> dict | None:
    if pair_id not in known_pairs() or wallet not in wallets_for_pair(pair_id):
        return None
    return compute_risk_score(wallet, pair_id)
