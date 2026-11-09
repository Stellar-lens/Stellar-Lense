"""Central configuration for stellar-lense-core, loaded from the environment.

pydantic-settings validates every field at import time, so a bad value
(e.g. ``RISK_SCORE_THRESHOLD=150``) fails fast with a readable error instead
of surfacing later as wrong scores.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # ── Horizon ───────────────────────────────────────────────────────────────
    horizon_url: str = "https://horizon.stellar.org"
    network: str = "testnet"

    # Horizon API version guard: `ingestion.http_client.VersionGuard` reads the
    # ``X-Stellar-Horizon-Version`` response header and refuses responses from
    # a server outside ``[horizon_min_version, horizon_max_version)``, so a
    # breaking schema change can't silently corrupt ingested trades. Disable
    # only for private Horizon nodes that strip the header.
    horizon_min_version: str = "2.0.0"
    horizon_max_version: str = "4.0.0"
    horizon_tested_version: str = "2.28.0"
    horizon_version_check_enabled: bool = True

    # Client-side rate limiting and retry policy for Horizon requests.
    # ``horizon_max_retry_delay`` also caps any server-sent Retry-After.
    horizon_rate_limit_rps: float = 5.0
    horizon_rate_burst: float = 10.0
    horizon_max_retries: int = 5
    horizon_base_retry_delay: float = 1.0
    horizon_max_retry_delay: float = 60.0

    # How far back `load_historical_trades` pages when no lookback is given.
    trade_history_lookback_days: int = 30

    # ── Detection ─────────────────────────────────────────────────────────────
    feature_engine_jit_enabled: bool = True
    benford_mad_threshold: float = 0.015
    risk_score_threshold: int = 70

    # ── Storage ───────────────────────────────────────────────────────────────
    model_dir: str = "./models"
    db_path: str = "./stellar_lense.db"

    # ── Observability ─────────────────────────────────────────────────────────
    # When False, ingestion/metrics.py returns a no-op collector.
    metrics_enabled: bool = True

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("trade_history_lookback_days", "horizon_max_retries", mode="before")
    @classmethod
    def must_be_positive(cls, v: object) -> object:
        if int(v) <= 0:
            raise ValueError("must be a positive integer")
        return v

    @field_validator("risk_score_threshold", mode="before")
    @classmethod
    def valid_score_threshold(cls, v: object) -> object:
        val = int(v)
        if not (0 <= val <= 100):
            raise ValueError(f"RISK_SCORE_THRESHOLD {val} must be 0-100")
        return v

    @field_validator("benford_mad_threshold", mode="before")
    @classmethod
    def non_negative_float(cls, v: object) -> object:
        if float(v) < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("horizon_url", mode="before")
    @classmethod
    def valid_url(cls, v: object) -> object:
        s = str(v).strip()
        if not s:
            raise ValueError("must be a non-empty URL")
        if not (s.startswith("http://") or s.startswith("https://")):
            raise ValueError(f"{s!r} is not a valid URL (expected http/https scheme)")
        return s

    @field_validator("network", mode="before")
    @classmethod
    def valid_network(cls, v: object) -> object:
        val = str(v).strip().lower()
        if val not in ("testnet", "mainnet"):
            raise ValueError(f"NETWORK must be 'testnet' or 'mainnet', got {v!r}")
        return val


settings = Settings()
