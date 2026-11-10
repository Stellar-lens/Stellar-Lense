"""Ingest and score jobs: Horizon -> SQLite store -> per-wallet scores.

* `ingest`: for each configured pair, fetch trades newer than the newest one
  already stored (bounded by a lookback window and a per-pair cap), insert
  them, and refresh the pair's 24h market snapshot. Read-only against
  Horizon.
* `score`: for each pair, score every wallet with at least `min_trades`
  trades in the scoring window using `detection.scoring.score_wallet`, and
  save the results as a new score run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from detection.scoring import score_wallet, wallets_in
from ingestion.historical_loader import load_historical_trades
from ingestion.market_data import load_market_snapshot
from pipeline.store import Store

logger = logging.getLogger("stellar_lense.pipeline")

DEFAULT_PAIRS_FILE = Path(__file__).with_name("pairs.mainnet.json")


@dataclass(frozen=True)
class Pair:
    base: str
    counter: str

    @property
    def id(self) -> str:
        """Same format as `ingestion.data_models.Trade.asset_pair`."""
        return f"{self.base}/{self.counter}"


@dataclass(frozen=True)
class PairConfig:
    horizon_url: str
    network: str
    pairs: list[Pair]


def load_pairs(path: str | Path = DEFAULT_PAIRS_FILE) -> PairConfig:
    data = json.loads(Path(path).read_text())
    pairs = [Pair(p["base"], p["counter"]) for p in data["pairs"]]
    if not pairs:
        raise ValueError(f"{path} lists no pairs")
    return PairConfig(horizon_url=data["horizon_url"], network=data["network"], pairs=pairs)


def ingest(
    store: Store,
    config: PairConfig,
    lookback_hours: float = 24.0,
    max_trades_per_pair: int = 20_000,
    retention_days: float = 7.0,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(hours=lookback_hours)
    summary: dict[str, Any] = {}
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        for pair in config.pairs:
            started = datetime.now(timezone.utc)
            newest = store.newest_trade_time(pair.id)
            since = max(newest, window_start) if newest else window_start
            try:
                trades = load_historical_trades(
                    pair.base,
                    pair.counter,
                    since=since,
                    max_records=max_trades_per_pair,
                    horizon_url=config.horizon_url,
                    client=client,
                )
                inserted = store.insert_trades(pair.id, trades)
                snapshot = load_market_snapshot(
                    pair.base, pair.counter, now=now, horizon_url=config.horizon_url, client=client
                )
                store.save_market(pair.id, snapshot.as_dict())
                store.record_ingest(pair.id, started, len(trades), inserted, "ok")
                summary[pair.id] = {"fetched": len(trades), "inserted": inserted}
                logger.info("ingest %s: fetched=%d inserted=%d", pair.id, len(trades), inserted)
            except Exception as exc:  # one bad pair must not stop the others
                store.record_ingest(pair.id, started, 0, 0, "error", repr(exc))
                summary[pair.id] = {"error": repr(exc)}
                logger.warning("ingest %s failed: %r", pair.id, exc)
    finally:
        if owns_client:
            client.close()
    store.prune_trades(now - timedelta(days=retention_days))
    return summary


def score(
    store: Store,
    config: PairConfig,
    window_hours: float = 24.0,
    min_trades: int = 5,
    model_bundle: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)
    run_id = store.start_score_run(
        window_start,
        now,
        min_trades,
        method="ml" if model_bundle else "heuristic",
        model_id=model_bundle["model_id"] if model_bundle else None,
        model_trained_on=model_bundle["trained_on"] if model_bundle else None,
    )
    summary: dict[str, Any] = {"run_id": run_id, "pairs": {}}
    data_as_of: datetime | None = None
    try:
        for pair in config.pairs:
            trades = store.trades_for_pair(pair.id, since=window_start)
            if trades.empty:
                summary["pairs"][pair.id] = {"wallets": 0, "trades": 0}
                continue
            newest = trades["ledger_close_time"].max().to_pydatetime()
            data_as_of = max(data_as_of, newest) if data_as_of else newest
            results = []
            for wallet in wallets_in(trades):
                result = score_wallet(trades, wallet, model_bundle=model_bundle)
                if result["trade_count"] >= min_trades:
                    results.append(result)
            store.save_scores(run_id, pair.id, results)
            summary["pairs"][pair.id] = {"wallets": len(results), "trades": len(trades)}
            logger.info("score %s: %d wallets from %d trades", pair.id, len(results), len(trades))
    except Exception:
        store.finish_score_run(run_id, "error", data_as_of)
        raise
    store.finish_score_run(run_id, "ok", data_as_of)
    summary["data_as_of"] = data_as_of
    return summary
