"""Wallet allowlist and denylist management with audit trail (Issue #181).

All persistence is delegated to :mod:`detection.wallet_override_store`, which
owns the ``wallet_overrides`` schema and is the same store the scoring path
reads through (``api/main.py``).  This router previously created its own copy
of the table with a divergent schema (no ``entry_id`` column); whichever module
ran ``CREATE TABLE IF NOT EXISTS`` first won, so inserts through this router
failed with an ``IntegrityError`` whenever the store had initialised the table
first.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import require_admin_key
from detection.wallet_override_store import (
    add_override,
    list_overrides,
    remove_override,
)

router = APIRouter(prefix="/admin", tags=["Allowlist / Denylist"])


class OverrideRequest(BaseModel):
    wallet: str
    reason: str = ""
    added_by: str = ""


def _add(list_type: str, body: OverrideRequest) -> dict:
    """Add an override, surfacing a duplicate active entry as 409."""
    try:
        return add_override(
            wallet=body.wallet,
            list_type=list_type,
            reason=body.reason,
            added_by=body.added_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _remove(list_type: str, wallet: str, removed_by: str) -> dict:
    """Soft-delete an override, surfacing a missing entry as 404."""
    removed = remove_override(wallet, list_type, removed_by or "unknown")
    if removed is None:
        raise HTTPException(status_code=404, detail=f"Wallet {wallet!r} not in {list_type}")
    return {"removed": True, **removed}


@router.post(
    "/allowlist",
    status_code=201,
    summary="Add wallet to allowlist",
    description="Allowlisted wallets return score=0 with override='allowlisted' immediately.",
    dependencies=[Depends(require_admin_key)],
)
def add_to_allowlist(body: OverrideRequest) -> dict:
    return _add("allowlist", body)


@router.post(
    "/denylist",
    status_code=201,
    summary="Add wallet to denylist",
    description="Denylisted wallets return score=100 with override='denylisted' immediately.",
    dependencies=[Depends(require_admin_key)],
)
def add_to_denylist(body: OverrideRequest) -> dict:
    return _add("denylist", body)


@router.get(
    "/allowlist",
    summary="List allowlist entries",
    description="Returns all allowlist entries (including soft-deleted) with pagination.",
    dependencies=[Depends(require_admin_key)],
)
def list_allowlist(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    return list_overrides("allowlist", limit=page_size, offset=(page - 1) * page_size)


@router.get(
    "/denylist",
    summary="List denylist entries",
    description="Returns all denylist entries (including soft-deleted) with pagination.",
    dependencies=[Depends(require_admin_key)],
)
def list_denylist(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    return list_overrides("denylist", limit=page_size, offset=(page - 1) * page_size)


@router.delete(
    "/allowlist/{wallet}",
    summary="Remove wallet from allowlist",
    description="Soft-deletes the allowlist entry; history is preserved with removed_at timestamp.",
    dependencies=[Depends(require_admin_key)],
)
def remove_from_allowlist(wallet: str, removed_by: str = "") -> dict:
    return _remove("allowlist", wallet, removed_by)


@router.delete(
    "/denylist/{wallet}",
    summary="Remove wallet from denylist",
    description="Soft-deletes the denylist entry; history is preserved with removed_at timestamp.",
    dependencies=[Depends(require_admin_key)],
)
def remove_from_denylist(wallet: str, removed_by: str = "") -> dict:
    return _remove("denylist", wallet, removed_by)
