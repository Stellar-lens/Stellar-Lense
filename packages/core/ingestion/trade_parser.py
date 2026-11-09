"""Parse raw Horizon `/trades` records into `Trade` models."""

from ingestion.data_models import Asset, Trade, TradeType


def parse_trade(record: dict) -> Trade:
    """Convert a raw Horizon `/trades` record into a `Trade` model.

    Horizon's `/trades` endpoint returns both order-book and AMM pool
    trades (CAP-38). A pool trade carries ``trade_type="liquidity_pool"``
    and a ``base_liquidity_pool_id``/``counter_liquidity_pool_id`` in place of
    a counterparty account — that side maps to ``counter_account=None`` plus
    ``liquidity_pool_id`` rather than a fabricated wallet.
    """
    base_asset = Asset(
        code=record.get("base_asset_code", "XLM"),
        issuer=record.get("base_asset_issuer"),
    )
    counter_asset = Asset(
        code=record.get("counter_asset_code", "XLM"),
        issuer=record.get("counter_asset_issuer"),
    )
    is_pool_trade = record.get("trade_type") == "liquidity_pool"
    liquidity_pool_id = record.get("base_liquidity_pool_id") or record.get(
        "counter_liquidity_pool_id"
    )
    return Trade(
        id=record["id"],
        paging_token=str(record.get("paging_token") or record["id"]),
        ledger_close_time=record["ledger_close_time"],
        base_account=record.get("base_account") or "",
        counter_account=record.get("counter_account"),
        base_asset=base_asset,
        counter_asset=counter_asset,
        base_amount=float(record["base_amount"]),
        counter_amount=float(record["counter_amount"]),
        price=float(record["price"]["n"]) / float(record["price"]["d"]),
        base_is_seller=record["base_is_seller"],
        trade_type=TradeType.LIQUIDITY_POOL if is_pool_trade else TradeType.ORDERBOOK,
        liquidity_pool_id=liquidity_pool_id,
    )


# Backwards-compatible private alias (older callers imported `_parse_trade`).
_parse_trade = parse_trade
