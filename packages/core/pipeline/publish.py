"""Publish the latest score run to the on-chain registry.

For each pair in the latest completed run: the pair aggregate
(average/max/flagged/total) and the `top_k` highest wallet scores, in
batches of `batch_size` per transaction. A run is published at most once
per contract (tracked in the store's `published_runs` table), so calling
this on every pipeline loop is cheap when nothing new was scored.

Only Stellar account wallets (G...) are published; the registry keys
scores by `Address`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pipeline.store import Store

logger = logging.getLogger("stellar_lense.publish")

ALERT_THRESHOLD = 50  # matches apps/api/api/alerts.py


def _epoch(value: datetime) -> int:
    return int(value.timestamp())


def plan(store: Store, top_k: int = 10) -> dict[str, Any] | None:
    """What would be published for the latest run (no network access)."""
    run = store.latest_score_run()
    if run is None:
        return None
    pairs = []
    for pair in store.pairs_scored(run["id"]):
        scores = store.scores(run["id"], pair)
        values = [s["score"] for s in scores]
        as_of = max(_epoch(s["timestamp"]) for s in scores)
        pairs.append(
            {
                "pair": pair,
                "aggregate": {
                    "average": round(sum(values) / len(values)),
                    "max": max(values),
                    "flagged": sum(v >= ALERT_THRESHOLD for v in values),
                    "total": len(values),
                    "as_of": as_of,
                },
                "wallets": [
                    {
                        "wallet": s["wallet"],
                        "pair": pair,
                        "score": s["score"],
                        "confidence": round(s["confidence"]),
                        "method": s["method"],
                        "as_of": _epoch(s["timestamp"]),
                    }
                    for s in scores[:top_k]
                    if s["wallet"].startswith("G")
                ],
            }
        )
    return {"run_id": run["id"], "pairs": pairs}


def publish(store: Store, client, signer, top_k: int = 10, batch_size: int = 20) -> dict[str, Any]:
    """Push the latest run via `client` (a `pipeline.soroban.RegistryClient`)."""
    work = plan(store, top_k)
    if work is None:
        return {"status": "nothing_scored"}
    if store.was_published(work["run_id"], client.contract_id):
        return {"status": "already_published", "run_id": work["run_id"]}

    txs = 0
    for p in work["pairs"]:
        a = p["aggregate"]
        # The registry requires average <= max; rounding can't break that,
        # but guard anyway so one odd pair can't fail the whole run.
        client.submit_pair_score(
            signer, p["pair"], min(a["average"], a["max"]), a["max"], a["flagged"], a["total"], a["as_of"]
        )
        txs += 1
        rows = p["wallets"]
        for i in range(0, len(rows), batch_size):
            client.submit_scores(signer, rows[i : i + batch_size])
            txs += 1
        logger.info("published %s: aggregate + %d wallets", p["pair"], len(rows))

    store.mark_published(work["run_id"], client.contract_id, txs)
    return {"status": "published", "run_id": work["run_id"], "transactions": txs}
