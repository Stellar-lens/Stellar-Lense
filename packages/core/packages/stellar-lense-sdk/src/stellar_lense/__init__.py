"""stellar-lense-sdk: a typed Python client for the StellarLense wash-trading
detection API.

    from stellar_lense import StellarLenseClient

    client = StellarLenseClient(base_url="https://api.stellar-lense.io", api_key="...")
    result = client.get_score("GABC...")
"""

from .async_client import AsyncStellarLenseClient
from .client import StellarLenseClient
from .exceptions import StellarLenseAPIError, StellarLenseError
from .models import (
    AssetRiskRanking,
    CounterfactualResponse,
    CounterfactualResult,
    CrossChainLink,
    Dispute,
    DisputeCreated,
    HealthStatus,
    RiskScore,
    ShapContribution,
    WalletScoresResponse,
    WebhookCreated,
    WebhookSubscriber,
)

__version__ = "0.1.0"

__all__ = [
    "StellarLenseClient",
    "AsyncStellarLenseClient",
    "StellarLenseError",
    "StellarLenseAPIError",
    "RiskScore",
    "WalletScoresResponse",
    "CrossChainLink",
    "ShapContribution",
    "CounterfactualResponse",
    "CounterfactualResult",
    "AssetRiskRanking",
    "WebhookSubscriber",
    "WebhookCreated",
    "Dispute",
    "DisputeCreated",
    "HealthStatus",
    "__version__",
]
