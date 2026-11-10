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

    Live mode: one point per completed scoring run (timestamp = the run's
    window end). Demo mode: recomputed at each distinct seeded trade time."""

    timestamp: datetime
    average_score: float
    max_score: int


class ScoringInfo(BaseModel):
    """How the scores currently served were produced."""

    method: Literal["heuristic", "ml"]
    model: ModelInfo | None = None
    min_trades: int
    window_start: datetime | None = None
    window_end: datetime | None = None


class Meta(BaseModel):
    """Provenance of the data behind every other endpoint.

    `mode` is "live" (Stellar network data ingested by the pipeline) or
    "demo" (hard-coded synthetic trades; `notice` explains). `data_as_of`
    is the close time of the newest trade the current scores are based on.
    """

    mode: Literal["live", "demo"]
    network: str | None
    data_as_of: datetime | None
    scored_at: datetime | None
    last_ingest: datetime | None
    pairs_tracked: int
    scoring: ScoringInfo
    notice: str | None = None


class MarketData(BaseModel):
    """24h market summary for a pair from Horizon trade aggregations.

    `price` is in counter-asset units per base unit (null if no trades in
    the window); `change_24h_pct` runs from the first hourly candle's open
    to the latest close."""

    asset_pair: str
    price: float | None
    change_24h_pct: float | None
    base_volume_24h: float
    counter_volume_24h: float
    trade_count_24h: int
    window_start: datetime
    window_end: datetime
    fetched_at: datetime
