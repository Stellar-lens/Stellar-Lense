"""Where the API's data comes from.

* Live (default): reads the SQLite store written by packages/core's pipeline
  (`python -m pipeline run`) at DB_PATH. Serves the latest completed score
  run; earlier runs are the score history.
* Demo (DEMO_MODE=1): api/demo.py's 12 hard-coded synthetic trades.

Routes call `backend()` and never branch on the mode themselves.
"""

from __future__ import annotations

import os
from functools import lru_cache
from types import ModuleType
from typing import Protocol

from api import demo
from api.alerts import ALERT_THRESHOLD, to_alert
from pipeline.store import Store


class NoDataYet(Exception):
    """Live mode, but the pipeline hasn't completed a score run yet."""


class Backend(Protocol):
    def meta(self) -> dict: ...
    def known_pairs(self) -> list[str]: ...
    def pair_scores(self, pair: str) -> list[dict] | None: ...
    def wallet_score(self, wallet: str, pair: str) -> dict | None: ...
    def recent_alerts(self, limit: int = 20) -> list[dict]: ...
    def asset_risk_ranking(self) -> list[dict]: ...
    def pair_score_history(self, pair: str) -> list[dict]: ...
    def market(self) -> list[dict]: ...


class LiveBackend:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _store(self) -> Store:
        if not os.path.exists(self.db_path):
            raise NoDataYet(f"no database at {self.db_path}; run the pipeline first")
        return Store(self.db_path, readonly=True)

    def _run(self) -> tuple[Store, dict]:
        store = self._store()
        run = store.latest_score_run()
        if run is None:
            raise NoDataYet("the pipeline hasn't completed a score run yet")
        return store, run

    def meta(self) -> dict:
        store, run = self._run()
        model = (
            {"model_id": run["model_id"], "trained_on": run["model_trained_on"]}
            if run["model_id"]
            else None
        )
        return {
            "mode": "live",
            "network": os.environ.get("STELLAR_NETWORK", "mainnet"),
            "data_as_of": run["data_as_of"],
            "scored_at": run["finished_at"],
            "last_ingest": store.last_ingest(),
            "pairs_tracked": len(store.pairs_scored(run["id"])),
            "scoring": {
                "method": run["method"],
                "model": model,
                "min_trades": run["min_trades"],
                "window_start": run["window_start"],
                "window_end": run["window_end"],
            },
            "notice": None,
        }

    def known_pairs(self) -> list[str]:
        store, run = self._run()
        return store.pairs_scored(run["id"])

    def pair_scores(self, pair: str) -> list[dict] | None:
        store, run = self._run()
        if pair not in store.pairs_scored(run["id"]):
            return None
        return store.scores(run["id"], pair)

    def wallet_score(self, wallet: str, pair: str) -> dict | None:
        store, run = self._run()
        found = store.scores(run["id"], pair, wallet)
        return found[0] if found else None

    def recent_alerts(self, limit: int = 20) -> list[dict]:
        store, run = self._run()
        flagged = [s for s in store.scores(run["id"]) if s["score"] >= ALERT_THRESHOLD]
        flagged.sort(key=lambda s: s["score"], reverse=True)
        return [to_alert(s) for s in flagged[:limit]]

    def asset_risk_ranking(self) -> list[dict]:
        store, run = self._run()
        rankings = []
        for pair in store.pairs_scored(run["id"]):
            values = [s["score"] for s in store.scores(run["id"], pair)]
            rankings.append(
                {
                    "asset_pair": pair,
                    "average_score": round(sum(values) / len(values), 2),
                    "max_score": max(values),
                    "flagged_wallets": sum(1 for v in values if v >= ALERT_THRESHOLD),
                    "total_wallets": len(values),
                }
            )
        rankings.sort(key=lambda r: r["average_score"], reverse=True)
        return rankings

    def pair_score_history(self, pair: str) -> list[dict]:
        return self._store().pair_history(pair)

    def market(self) -> list[dict]:
        rows = self._store().market()
        return [
            {
                "asset_pair": r["pair"],
                "price": r["price"],
                "change_24h_pct": r["change_24h_pct"],
                "base_volume_24h": r["base_volume_24h"],
                "counter_volume_24h": r["counter_volume_24h"],
                "trade_count_24h": r["trade_count_24h"],
                "window_start": r["window_start"],
                "window_end": r["window_end"],
                "fetched_at": r["fetched_at"],
            }
            for r in rows
        ]


def demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "") in ("1", "true", "yes")


@lru_cache(maxsize=1)
def _live(db_path: str) -> LiveBackend:
    return LiveBackend(db_path)


def backend() -> Backend | ModuleType:
    if demo_mode():
        return demo
    return _live(os.environ.get("DB_PATH", "./data/stellar_lense.db"))
