"""24h market snapshot for an SDEX pair from Horizon `/trade_aggregations`.

Horizon buckets trades into OHLCV candles server-side. We ask for hourly
candles covering the last 24 hours and derive:

* ``price``: close of the most recent candle (counter units per base unit),
* ``change_24h_pct``: from the first candle's open to that close,
* ``base_volume_24h`` / ``counter_volume_24h`` / ``trade_count_24h``: sums.

Hours with no trades produce no candle, so a quiet pair can have fewer than
24 buckets; a pair with no trades at all yields ``price=None``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import httpx

from config.settings import settings
from ingestion.historical_loader import _asset_params
from ingestion.http_client import get_with_retry

HOUR_MS = 3_600_000


@dataclass(frozen=True)
class MarketSnapshot:
    base_asset: str
    counter_asset: str
    price: float | None
    change_24h_pct: float | None
    base_volume_24h: float
    counter_volume_24h: float
    trade_count_24h: int
    window_start: datetime
    window_end: datetime

    def as_dict(self) -> dict:
        return asdict(self)


def snapshot_from_candles(
    base_asset: str,
    counter_asset: str,
    candles: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> MarketSnapshot:
    """Reduce Horizon trade-aggregation records (oldest first) to a snapshot."""
    if not candles:
        return MarketSnapshot(base_asset, counter_asset, None, None, 0.0, 0.0, 0, window_start, window_end)
    first_open = float(candles[0]["open"])
    last_close = float(candles[-1]["close"])
    change = (last_close - first_open) / first_open * 100 if first_open else None
    return MarketSnapshot(
        base_asset=base_asset,
        counter_asset=counter_asset,
        price=last_close,
        change_24h_pct=change,
        base_volume_24h=sum(float(c["base_volume"]) for c in candles),
        counter_volume_24h=sum(float(c["counter_volume"]) for c in candles),
        trade_count_24h=sum(int(c["trade_count"]) for c in candles),
        window_start=window_start,
        window_end=window_end,
    )


def load_market_snapshot(
    base_asset: str,
    counter_asset: str,
    *,
    now: datetime | None = None,
    horizon_url: str | None = None,
    client: httpx.Client | None = None,
) -> MarketSnapshot:
    """Fetch hourly candles for the last 24h and summarise them."""
    now = now or datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000) // HOUR_MS * HOUR_MS + HOUR_MS  # include current hour
    start_ms = end_ms - 24 * HOUR_MS
    params: dict[str, str | int] = {
        "start_time": start_ms,
        "end_time": end_ms,
        "resolution": HOUR_MS,
        "order": "asc",
        "limit": 200,
    }
    params.update(_asset_params("base", base_asset))
    params.update(_asset_params("counter", counter_asset))

    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        response = get_with_retry(
            client, f"{horizon_url or settings.horizon_url}/trade_aggregations", params=params
        )
        candles = response.json()["_embedded"]["records"]
    finally:
        if owns_client:
            client.close()

    window_start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    window_end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    # Drop any candle Horizon returns outside the window (defensive).
    candles = [c for c in candles if start_ms <= int(c["timestamp"]) < end_ms]
    return snapshot_from_candles(base_asset, counter_asset, candles, window_start, window_end)
