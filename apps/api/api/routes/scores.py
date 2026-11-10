"""GET /score/{wallet}/{pair} — StellarLense Risk Score lookup."""

import re

from fastapi import APIRouter, HTTPException

from api.schemas import RiskScore
from api.storage import backend

router = APIRouter(prefix="/score", tags=["scores"])

_STELLAR_ACCOUNT = re.compile(r"^G[A-Z2-7]{55}$")


@router.get("/{wallet}/{pair:path}", response_model=RiskScore)
def get_score(wallet: str, pair: str) -> RiskScore:
    """Return the current StellarLense Risk Score for `wallet` on `pair`.

    `pair` is `BASE/COUNTER` with each asset `XLM` or `CODE:ISSUER`, e.g.
    `XLM/USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN`.
    """
    if not _STELLAR_ACCOUNT.match(wallet):
        raise HTTPException(status_code=400, detail="Invalid Stellar account ID format")

    data = backend()
    if pair not in data.known_pairs():
        raise HTTPException(status_code=404, detail=f"Unknown asset pair: {pair}")
    result = data.wallet_score(wallet, pair)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No score for wallet {wallet} on {pair}")
    return RiskScore.from_storage_result(result)
