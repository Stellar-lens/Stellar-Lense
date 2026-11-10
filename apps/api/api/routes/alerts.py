"""GET /alerts/recent — wallet/pair combinations at or above the alert threshold."""

from fastapi import APIRouter, Query

from api.schemas import Alert
from api.storage import backend

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/recent", response_model=list[Alert])
def get_recent_alerts(limit: int = Query(default=20, ge=1, le=100)) -> list[Alert]:
    """Return the highest-risk wallet/asset-pair combinations currently flagged."""
    return [Alert(**a) for a in backend().recent_alerts(limit=limit)]
