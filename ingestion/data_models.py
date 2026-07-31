"""Pydantic schemas for raw data pulled from the Stellar Horizon API.

These models are the shared contract between the ingestion layer and the
detection layer (Benford engine + feature engineering). Keep field names
stable — downstream code and the `ledgerlens-core` shared types mirror them.

Precision Handling
------------------
Financial fields (amounts, prices) use Decimal type with validation to prevent
float precision errors. See utils.decimal_guards for the precision guard system.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class Asset(BaseModel):
    code: str
    issuer: str | None = None  # None / "native" for XLM

    def pair_id(self, other: "Asset") -> str:
        return f"{self.code}:{self.issuer or 'native'}/{other.code}:{other.issuer or 'native'}"


class Trade(BaseModel):
    """A single executed trade on the SDEX.

    Precision Note
    --------------
    Amount and price fields use Decimal type to prevent floating-point
    precision errors. Stellar amounts have 7-decimal precision (stroops).
    Values are validated on initialization to ensure they meet Stellar
    constraints (7 decimals max, int64 bounds).
    """

    trade_id: str
    ledger_close_time: datetime
    base_account: str
    counter_account: str
    base_asset: Asset
    counter_asset: Asset
    base_amount: Decimal
    counter_amount: Decimal
    price: Decimal

    @field_validator("base_amount", "counter_amount", "price", mode="before")
    @classmethod
    def validate_stellar_amounts(cls, v):
        """Validate amounts meet Stellar precision requirements."""
        from utils.decimal_guards import validate_stellar_amount

        return validate_stellar_amount(v)

    @property
    def amount(self) -> Decimal:
        """Primary amount used for Benford digit analysis."""
        return self.base_amount


class OrderBookEvent(BaseModel):
    """Order placement / cancellation event.

    Precision Note
    --------------
    Amount and price fields use Decimal type to prevent floating-point
    precision errors. Values are validated on initialization.
    """

    event_id: str
    account: str
    ledger_close_time: datetime
    selling: Asset
    buying: Asset
    amount: Decimal
    price: Decimal
    action: str = Field(description="one of: created, cancelled, updated")

    @field_validator("amount", "price", mode="before")
    @classmethod
    def validate_stellar_amounts(cls, v):
        """Validate amounts meet Stellar precision requirements."""
        from utils.decimal_guards import validate_stellar_amount

        return validate_stellar_amount(v)


class AccountActivity(BaseModel):
    """Lightweight summary of an account, used for wallet graph features."""

    account_id: str
    account_created_at: datetime
    funding_account: str | None = None
    home_domain: str | None = None


class BotFingerprint(BaseModel):
    """Bot detection fingerprint extracted from Horizon event patterns."""

    account_id: str
    trust_line_creation_latency_seconds: float | None = Field(
        default=None,
        description="Time in seconds from account creation to first trust line"
    )
    inter_trade_interval_cv: float | None = Field(
        default=None,
        description="Coefficient of variation of inter-trade intervals (low=robotic)"
    )
    account_management_cluster_score: float = Field(
        default=0.0,
        description="Entropy of operation type distribution (low=clustered=bot)"
    )
    is_valid: bool = Field(
        default=True,
        description="False if insufficient data (< 5 trades)"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for bot fingerprint validity [0, 1]"
    )
