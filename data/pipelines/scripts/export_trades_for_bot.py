"""Export historical SDEX trades as OHLCV candles for apps/bot's backtester.

apps/bot (TypeScript) cannot import this package's Python ingestion code
directly, so this script is the reuse boundary: it drives the real
`ingestion.historical_loader.load_trades()` against Horizon, aggregates the
resulting trades into candles with the same resample convention used by
`features/ohlcv_features.py` (label="left", closed="left"), and writes them
as newline-delimited JSON that apps/bot reads as its historical data source.

Usage:
    python -m scripts.export_trades_for_bot \\
        --base XLM --counter USDC \\
        --counter-issuer GA5ZSEJYBY3RJRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN \\
        --resolution 1h \\
        --limit 500 \\
        --output ../../apps/bot/fixtures/xlm-usdc-1h.ndjson
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from stellar_sdk import Asset as SdkAsset

from ingestion.historical_loader import load_trades

# Mirrors features/ohlcv_features.py's _PANDAS_FREQ: pandas deprecated the
# lowercase "m" minute alias, so the CLI-facing "1m"/"5m"/"15m" strings need
# translating before they reach resample().
_PANDAS_FREQ = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}


def _asset(code: str, issuer: str | None) -> SdkAsset:
    return SdkAsset.native() if code.upper() == "XLM" and not issuer else SdkAsset(code, issuer)


def export(
    base_code: str,
    base_issuer: str | None,
    counter_code: str,
    counter_issuer: str | None,
    resolution: str,
    limit: int | None,
    start_time: datetime | None,
    output: Path,
) -> int:
    if resolution not in _PANDAS_FREQ:
        raise ValueError(f"Unsupported resolution {resolution!r}. Allowed: {sorted(_PANDAS_FREQ)}")

    base = _asset(base_code, base_issuer)
    counter = _asset(counter_code, counter_issuer)

    rows = []
    for trade in load_trades(base, counter, start_time=start_time):
        rows.append(
            {
                "ledger_close_time": trade.ledger_close_time,
                "price": float(trade.price),
                "amount": float(trade.base_amount),
            }
        )
        if limit is not None and len(rows) >= limit:
            break

    if not rows:
        output.write_text("")
        return 0

    df = pd.DataFrame(rows)
    df["ledger_close_time"] = pd.to_datetime(df["ledger_close_time"], utc=True)
    df = df.sort_values("ledger_close_time").set_index("ledger_close_time")

    freq = _PANDAS_FREQ[resolution]
    g = df.resample(freq, label="left", closed="left")

    candles = pd.DataFrame(
        {
            "open": g["price"].first(),
            "high": g["price"].max(),
            "low": g["price"].min(),
            "close": g["price"].last(),
            "volume": g["amount"].sum(),
            "trades": g["price"].count(),
        }
    ).dropna(subset=["open"])

    with output.open("w") as fh:
        for ts, row in candles.iterrows():
            fh.write(
                json.dumps(
                    {
                        "time": ts.isoformat(),
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "trades": int(row["trades"]),
                    }
                )
                + "\n"
            )

    return len(candles)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base asset code, e.g. XLM")
    parser.add_argument("--base-issuer", default=None)
    parser.add_argument("--counter", required=True, help="Counter asset code, e.g. USDC")
    parser.add_argument("--counter-issuer", default=None)
    parser.add_argument("--resolution", default="1h", choices=sorted(_PANDAS_FREQ))
    parser.add_argument("--limit", type=int, default=None, help="Max raw trades to fetch")
    parser.add_argument("--start", default=None, help="ISO8601 start time (UTC)")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    start_time = datetime.fromisoformat(args.start).replace(tzinfo=UTC) if args.start else None
    args.output.parent.mkdir(parents=True, exist_ok=True)

    n = export(
        args.base,
        args.base_issuer,
        args.counter,
        args.counter_issuer,
        args.resolution,
        args.limit,
        start_time,
        args.output,
    )
    print(f"Wrote {n} candles to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
