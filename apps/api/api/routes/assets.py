"""GET /assets/risk-ranking — asset pairs ranked by aggregate risk.
GET /assets/{pair}/scores — every wallet scored on one pair, for the asset
detail view's drill-down (each entry carries the same SHAP attributions
as GET /score/{wallet}/{pair}).
GET /assets/{pair}/score-history — the pair's derived score history, for
correlating against news timing (see api.storage.pair_score_history)."""

from fastapi import APIRouter, HTTPException

from api import storage
from api.schemas import AssetRiskRanking, RiskScore, ScoreHistoryPoint

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/risk-ranking", response_model=list[AssetRiskRanking])
def get_risk_ranking() -> list[AssetRiskRanking]:
    """Return asset pairs ranked by average wallet risk score, highest first."""
    return [AssetRiskRanking(**r) for r in storage.asset_risk_ranking()]


@router.get("/{pair:path}/scores", response_model=list[RiskScore])
def get_pair_scores(pair: str) -> list[RiskScore]:
    """Return every wallet's risk score on `pair`, highest score first."""
    if pair not in storage.known_pairs():
        raise HTTPException(status_code=404, detail=f"Unknown asset pair: {pair}")

    results = [
        storage.compute_risk_score(wallet, pair)
        for wallet in storage.wallets_for_pair(pair)
    ]
    results.sort(key=lambda r: r["score"], reverse=True)
    return [RiskScore.from_storage_result(r) for r in results]


@router.get("/{pair:path}/score-history", response_model=list[ScoreHistoryPoint])
def get_pair_score_history(pair: str) -> list[ScoreHistoryPoint]:
    """Return `pair`'s derived aggregate score history, oldest first."""
    if pair not in storage.known_pairs():
        raise HTTPException(status_code=404, detail=f"Unknown asset pair: {pair}")
    return [ScoreHistoryPoint(**p) for p in storage.pair_score_history(pair)]
