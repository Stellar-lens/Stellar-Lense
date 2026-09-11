"""Response schemas for the StellarLense public REST API."""

from datetime import datetime

from pydantic import BaseModel


class BenfordReport(BaseModel):
    """Leading-digit distribution analysis for a wallet's trade amounts."""

    sample_size: int
    chi_square: float
    mad: float
    z_scores: dict[int, float]
    non_conforming: bool


class RiskScore(BaseModel):
    """StellarLense Risk Score for a wallet on a given asset pair.

    `features` and `benford` are always present (the heuristic path always
    computes them). `shap` is only present when the trained ML ensemble
    artifact is available — see detection/model_inference.py — and is
    `None` otherwise, e.g. when falling back to the Phase 1 heuristic.
    """

    wallet: str
    asset_pair: str
    score: int
    benford_flag: bool
    ml_flag: bool
    confidence: float
    timestamp: datetime
    features: dict[str, float]
    benford: BenfordReport
    shap: dict[str, float] | None = None

    @classmethod
    def from_storage_result(cls, result: dict) -> "RiskScore":
        """Build from the raw dict shape detection.model_inference.score_wallet
        (via api.storage.compute_risk_score) returns."""
        components = result["components"]
        return cls(
            wallet=result["wallet"],
            asset_pair=result["asset_pair"],
            score=result["score"],
            benford_flag=result["benford_flag"],
            ml_flag=result["ml_flag"],
            confidence=result["confidence"],
            timestamp=result["timestamp"],
            features=components["features"],
            benford=components["benford"],
            shap=components.get("shap"),
        )


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


class ScoreHistoryPoint(BaseModel):
    """One point in a pair's aggregate risk-score history.

    Not a persisted time series — this demo API has no running pipeline
    writing scores over time (see api.storage.pair_score_history) — but a
    genuine derivation from the same seeded trade data, recomputed at each
    distinct trade timestamp for the pair, not fabricated values."""

    timestamp: datetime
    average_score: float
    max_score: int
