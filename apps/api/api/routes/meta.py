"""GET /meta — where the data comes from and how fresh it is."""

from fastapi import APIRouter

from api.schemas import Meta
from api.storage import backend

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=Meta)
def get_meta() -> Meta:
    """Data mode (live/demo), data-as-of time, and how scores were produced."""
    return Meta(**backend().meta())
