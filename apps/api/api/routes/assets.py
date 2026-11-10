"""GET /assets/risk-ranking — tracked pairs ranked by aggregate risk.
GET /assets/{pair}/scores — every scored wallet on one pair.
GET /assets/{pair}/score-history — the pair's aggregate score per scoring run."""

from fastapi import APIRouter, HTTPException

from api.schemas import AssetRiskRanking, RiskScore, ScoreHistoryPoint
from api.storage import backend

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/risk-ranking", response_model=list[AssetRiskRanking])
def get_risk_ranking() -> list[AssetRiskRanking]:
    """Return tracked pairs ranked by average wallet risk score, highest first."""
    return [AssetRiskRanking(**r) for r in backend().asset_risk_ranking()]


@router.get("/{pair:path}/scores", response_model=list[RiskScore])
def get_pair_scores(pair: str) -> list[RiskScore]:
    """Return every scored wallet on `pair`, highest score first."""
    results = backend().pair_scores(pair)
    if results is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset pair: {pair}")
    return [RiskScore.from_storage_result(r) for r in results]


@router.get("/{pair:path}/score-history", response_model=list[ScoreHistoryPoint])
def get_pair_score_history(pair: str) -> list[ScoreHistoryPoint]:
    """Return `pair`'s aggregate score history, oldest first."""
    data = backend()
    if pair not in data.known_pairs():
        raise HTTPException(status_code=404, detail=f"Unknown asset pair: {pair}")
    return [ScoreHistoryPoint(**p) for p in data.pair_score_history(pair)]
