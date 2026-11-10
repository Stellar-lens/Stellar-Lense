"""Historical trade ingestion from Stellar Horizon's `/trades` endpoint."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd
from pydantic import ValidationError

from config.settings import settings
from ingestion.trade_parser import parse_trade
from ingestion.http_client import AsyncHorizonClient, get_with_retry

PAGE_LIMIT = 200
logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _horizon_time(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_asset_pair(asset_pair: str) -> tuple[str, str]:
    try:
        base, counter = asset_pair.split("/", 1)
    except ValueError as exc:
        raise ValueError("asset_pair must be BASE/COUNTER") from exc
    if not base or not counter:
        raise ValueError("asset_pair must be BASE/COUNTER")
    return base, counter


def load_historical_trades(
    base_asset: str | None = None,
    counter_asset: str | None = None,
    lookback_days: int | None = None,
    *,
    since: datetime | None = None,
    max_records: int | None = None,
    horizon_url: str | None = None,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """Fetch trades newest-first from Horizon `/trades` and return a DataFrame.

    Paging stops at the first trade older than the lookback cutoff, at or
    before `since` (for incremental loads: pass the newest trade time you
    already have), or once `max_records` trades have been collected.
    Assets are ``"XLM"`` or ``"CODE:ISSUER"``.
    """
    lookback_days = lookback_days or settings.trade_history_lookback_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    if since is not None:
        cutoff = max(cutoff, _utc(since))
    params: dict[str, str | int] = {"limit": PAGE_LIMIT, "order": "desc"}
    if base_asset:
        params.update(_asset_params("base", base_asset))
    if counter_asset:
        params.update(_asset_params("counter", counter_asset))

    records: list[dict] = []
    url: str | None = f"{horizon_url or settings.horizon_url}/trades"
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        while url:
            response = get_with_retry(client, url, params=params)
            payload = response.json()
            page_records = payload["_embedded"]["records"]
            if not page_records:
                break
            for record in page_records:
                close_time = datetime.fromisoformat(
                    record["ledger_close_time"].replace("Z", "+00:00")
                )
                stale = close_time <= cutoff if since is not None else close_time < cutoff
                if stale:
                    return _to_dataframe(records)
                records.append(record)
                if max_records is not None and len(records) >= max_records:
                    return _to_dataframe(records)
            url = payload["_links"]["next"]["href"]
            params = {}
    finally:
        if owns_client:
            client.close()
    return _to_dataframe(records)


def _asset_params(prefix: str, asset: str) -> dict[str, str]:
    if ":" in asset:
        code, issuer = asset.split(":", 1)
        asset_type = "credit_alphanum12" if len(code) > 4 else "credit_alphanum4"
        return {
            f"{prefix}_asset_type": asset_type,
            f"{prefix}_asset_code": code,
            f"{prefix}_asset_issuer": issuer,
        }
    return {f"{prefix}_asset_type": "native"}


def _to_dataframe(records: list[dict]) -> pd.DataFrame:
    """Parse records, skipping any `Trade` rejects.

    Horizon does return trades the model can't represent, e.g. dust trades
    whose amount rounds to "0.0000000". One such record must not discard
    the rest of the page; skipped ids are logged and counted in
    ``df.attrs["skipped"]``.
    """
    parsed, skipped = [], []
    for record in records:
        try:
            parsed.append(parse_trade(record).model_dump())
        except ValidationError:
            skipped.append(record.get("id"))
    if skipped:
        logger.warning("skipped %d unparseable Horizon trade(s), e.g. %s", len(skipped), skipped[:3])
    df = pd.DataFrame(parsed)
    df.attrs["skipped"] = len(skipped)
    return df


async def async_load_historical_trades(
    base_asset: str | None = None,
    counter_asset: str | None = None,
    lookback_days: int | None = None,
    client: AsyncHorizonClient | None = None,
) -> pd.DataFrame:
    """Fetch historical trades sequentially using the shared async client."""
    if client is None:
        raise ValueError("client is required for async_load_historical_trades")
    lookback_days = lookback_days or settings.trade_history_lookback_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    params: dict[str, str | int] = {"limit": PAGE_LIMIT, "order": "desc"}
    if base_asset:
        params.update(_asset_params("base", base_asset))
    if counter_asset:
        params.update(_asset_params("counter", counter_asset))

    records: list[dict] = []
    path: str | None = "/trades"
    request_params: dict | None = params
    while path:
        payload = await client.get(path, params=request_params)
        page_records = payload.get("_embedded", {}).get("records", [])
        if not page_records:
            break
        for record in page_records:
            close_time = datetime.fromisoformat(
                record["ledger_close_time"].replace("Z", "+00:00")
            )
            if close_time < cutoff:
                return _to_dataframe(records)
            records.append(record)
        path = payload.get("_links", {}).get("next", {}).get("href") or None
        request_params = None
    return _to_dataframe(records)
