"""Response schemas for the StellarLense public REST API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class BenfordReport(BaseModel):
    """Leading-digit distribution analysis for a wallet's trade amounts.

    `non_conforming` is only ever true when `sufficient_sample` is: with too
    few trades a first-digit test says nothing, so it isn't used.
    """

    sample_size: int
    chi_square: float
    chi_square_pvalue: float
    mad: float
    z_scores: dict[int, float]
    sufficient_sample: bool
    non_conforming: bool


class ModelInfo(BaseModel):
    """Identity of the ML model that produced a score (method == "ml")."""

    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    trained_on: str


class RiskScore(BaseModel):
    """StellarLense Risk Score for a wallet on a given asset pair.

    `method` says how the score was produced: "heuristic" (a fixed weighted
    sum of the features below plus a capped Benford term; see
    packages/core/detection/scoring.py) or "ml" (a trained model, identified
    by `model`). `shap` is only present for "ml" scores.
    """

    wallet: str
    asset_pair: str
    score: int
    method: Literal["heuristic", "ml"]
    model: ModelInfo | None = None
    benford_flag: bool
    ml_flag: bool
    confidence: float
    trade_count: int
    timestamp: datetime
    features: dict[str, float]
    benford: BenfordReport
    shap: dict[str, float] | None = None

    @classmethod
    def from_storage_result(cls, result: dict) -> "RiskScore":
        """Build from the dict detection.scoring.score_wallet returns (plus
        the asset_pair/timestamp the storage layer adds)."""
        return cls(
            wallet=result["wallet"],
            asset_pair=result["asset_pair"],
            score=result["score"],
            method=result["method"],
            model=result["model"],
            benford_flag=result["benford_flag"],
            ml_flag=result["ml_flag"],
            confidence=result["confidence"],
            trade_count=result["trade_count"],
            timestamp=result["timestamp"],
            features=result["features"],
            benford=result["benford"],
            shap=result.get("shap"),
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
