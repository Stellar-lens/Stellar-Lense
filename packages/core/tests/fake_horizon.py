"""A tiny in-memory Horizon for tests: serves /trades (paged, desc) and
/trade_aggregations from a list of trade records."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx

USDC_ISSUER = "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"


def trade_record(
    i: int,
    when: datetime,
    base: str,
    counter: str | None,
    amount: float,
    base_is_seller: bool = True,
    price: tuple[int, int] = (1, 10),
) -> dict:
    record = {
        "id": f"{i}-0",
        "paging_token": f"{i}-0",
        "ledger_close_time": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_account": base,
        "base_asset_type": "native",
        "counter_asset_type": "credit_alphanum4",
        "counter_asset_code": "USDC",
        "counter_asset_issuer": USDC_ISSUER,
        "base_amount": f"{amount:.7f}",
        "counter_amount": f"{amount * price[0] / price[1]:.7f}",
        "price": {"n": price[0], "d": price[1]},
        "base_is_seller": base_is_seller,
        "trade_type": "orderbook" if counter else "liquidity_pool",
    }
    if counter:
        record["counter_account"] = counter
    else:
        record["base_liquidity_pool_id"] = "pool1"
    return record


class FakeHorizon:
    def __init__(self, records: list[dict], page_size: int = 3):
        # Newest first, like Horizon with order=desc.
        self.records = sorted(records, key=lambda r: r["ledger_close_time"], reverse=True)
        self.page_size = page_size
        self.requests: list[str] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport())

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        url = urlparse(str(request.url))
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        headers = {"X-Stellar-Horizon-Version": "2.28.0"}
        if url.path.endswith("/trades"):
            offset = int(q.get("cursor", 0))
            page = self.records[offset : offset + self.page_size]
            nxt = f"https://horizon.test/trades?cursor={offset + self.page_size}&order=desc"
            return httpx.Response(
                200,
                json={"_embedded": {"records": page}, "_links": {"next": {"href": nxt}}},
                headers=headers,
            )
        if url.path.endswith("/trade_aggregations"):
            return httpx.Response(200, json={"_embedded": {"records": self.candles(q)}}, headers=headers)
        return httpx.Response(404, headers=headers)

    def candles(self, q: dict) -> list[dict]:
        start, end, res = int(q["start_time"]), int(q["end_time"]), int(q["resolution"])
        buckets: dict[int, list[dict]] = {}
        for r in self.records:
            t = int(datetime.fromisoformat(r["ledger_close_time"].replace("Z", "+00:00")).timestamp() * 1000)
            if start <= t < end:
                buckets.setdefault(t // res * res, []).append(r)
        out = []
        for ts in sorted(buckets):
            rows = sorted(buckets[ts], key=lambda r: r["ledger_close_time"])
            prices = [r["price"]["n"] / r["price"]["d"] for r in rows]
            out.append(
                {
                    "timestamp": str(ts),
                    "trade_count": str(len(rows)),
                    "base_volume": str(sum(float(r["base_amount"]) for r in rows)),
                    "counter_volume": str(sum(float(r["counter_amount"]) for r in rows)),
                    "open": str(prices[0]),
                    "close": str(prices[-1]),
                }
            )
        return out


def wash_and_organic(now: datetime) -> list[dict]:
    """Two accounts round-tripping 20 times, plus a market maker trading
    40 times with 40 different takers, all within the last few hours."""
    records = []
    i = 0
    for k in range(20):
        i += 1
        records.append(
            trade_record(i, now - timedelta(minutes=200 - k * 2), "GWASHA", "GWASHB", 5000.0, k % 2 == 0)
        )
    for k in range(40):
        i += 1
        amount = [1872, 342, 91, 27840, 615, 1203, 187, 45, 9120, 2301][k % 10] + k
        records.append(
            trade_record(i, now - timedelta(minutes=300 - k * 7), "GMAKER", f"GTAKER{k}", float(amount), k % 3 == 0, (k + 9, 100))
        )
    return records
