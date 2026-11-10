"""GET /market — 24h price, change and volume per tracked pair.

Computed by the pipeline from Horizon /trade_aggregations (hourly candles
over the last 24h). Empty in demo mode: the demo never invents prices."""

from fastapi import APIRouter, HTTPException

from api.schemas import MarketData
from api.storage import backend

router = APIRouter(prefix="/market", tags=["market"])


@router.get("", response_model=list[MarketData])
def get_market() -> list[MarketData]:
    return [MarketData(**m) for m in backend().market()]


@router.get("/{pair:path}", response_model=MarketData)
def get_pair_market(pair: str) -> MarketData:
    for m in backend().market():
        if m["asset_pair"] == pair:
            return MarketData(**m)
    raise HTTPException(status_code=404, detail=f"No market data for {pair}")
