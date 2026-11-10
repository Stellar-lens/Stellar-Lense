"""Alert threshold and human-readable reasons, shared by both backends."""

# Risk score at or above this value generates an alert.
ALERT_THRESHOLD = 50


def alert_reason(score: dict) -> str:
    features = score["features"]
    reasons = []
    if score["benford_flag"]:
        reasons.append("non-conforming digit distribution")
    if features.get("round_trip_trade_frequency", 0) > 0:
        reasons.append("round-trip trading detected")
    if features.get("counterparty_concentration_ratio", 0) > 0.8:
        reasons.append("high counterparty concentration")
    if features.get("intra_minute_clustering_coefficient", 0) > 0.8:
        reasons.append("trades clustered within the same minute")
    return "; ".join(reasons) or "elevated risk score"


def to_alert(score: dict) -> dict:
    return {
        "id": f"{score['asset_pair']}:{score['wallet']}",
        "wallet": score["wallet"],
        "asset_pair": score["asset_pair"],
        "score": score["score"],
        "reason": alert_reason(score),
        "timestamp": score["timestamp"],
    }
