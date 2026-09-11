"""Response schemas for the LedgerLens public REST API."""

from datetime import datetime

from pydantic import BaseModel


class RiskScore(BaseModel):
    """LedgerLens Risk Score for a wallet on a given asset pair."""

    wallet: str
    asset_pair: str
    score: int
    benford_flag: bool
    ml_flag: bool
    confidence: float
    timestamp: datetime


class Alert(BaseModel):
    """A flagged wallet/asset-pair combination exceeding the alert threshold."""

    id: str
    wallet: str
    asset_pair: str
    score: int
    reason: str
    timestamp: datetime


class AssetRiskRanking(BaseModel):
    """Aggregate risk ranking for an asset pair across all scored wallets."""

    asset_pair: str
    average_score: float
    max_score: int
    flagged_wallets: int
    total_wallets: int
