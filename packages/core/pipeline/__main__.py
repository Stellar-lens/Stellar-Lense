"""Command line for the ingest -> score pipeline.

    python -m pipeline ingest        # pull recent trades + market data from Horizon
    python -m pipeline score         # score wallets from stored trades
    python -m pipeline run           # ingest then score, once
    python -m pipeline run --every 900   # ... and repeat every 15 minutes
    python -m pipeline healthcheck   # exit 0 once a completed score run exists

Configuration (environment variables):

    DB_PATH           SQLite file shared with apps/api (default ./data/stellar_lense.db)
    PAIRS_FILE        pair list JSON (default pipeline/pairs.mainnet.json)
    LOOKBACK_HOURS    how far back the first ingest reaches (default 24)
    MAX_TRADES_PER_PAIR  cap per pair per ingest run (default 20000)
    SCORE_WINDOW_HOURS   trades considered when scoring (default 24)
    MIN_TRADES        wallets with fewer trades in the window aren't scored (default 5)
    MODEL_PATH        optional ML bundle from scripts/train_model.py; heuristic if absent
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from pipeline.jobs import DEFAULT_PAIRS_FILE, ingest, load_pairs, score
from pipeline.store import Store


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _load_model():
    path = os.environ.get("MODEL_PATH")
    if not path:
        return None
    from detection.model import load_bundle

    bundle = load_bundle(path)
    if bundle is None:
        logging.warning("MODEL_PATH=%s not found; scoring with the heuristic", path)
    return bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("command", choices=["ingest", "score", "run", "healthcheck"])
    parser.add_argument("--every", type=float, default=0, help="repeat every N seconds")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    db_path = os.environ.get("DB_PATH", "./data/stellar_lense.db")
    if args.command == "healthcheck":
        if not os.path.exists(db_path):
            return 1
        return 0 if Store(db_path, readonly=True).latest_score_run() else 1

    store = Store(db_path)
    config = load_pairs(os.environ.get("PAIRS_FILE", DEFAULT_PAIRS_FILE))
    model = _load_model() if args.command in ("score", "run") else None

    while True:
        if args.command in ("ingest", "run"):
            ingest(
                store,
                config,
                lookback_hours=_env_float("LOOKBACK_HOURS", 24),
                max_trades_per_pair=int(_env_float("MAX_TRADES_PER_PAIR", 20_000)),
            )
        if args.command in ("score", "run"):
            result = score(
                store,
                config,
                window_hours=_env_float("SCORE_WINDOW_HOURS", 24),
                min_trades=int(_env_float("MIN_TRADES", 5)),
                model_bundle=model,
            )
            logging.info("score run %s complete; data as of %s", result["run_id"], result["data_as_of"])
        if not args.every:
            return 0
        time.sleep(args.every)


if __name__ == "__main__":
    sys.exit(main())
