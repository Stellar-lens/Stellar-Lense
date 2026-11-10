"""SQLite store shared by the pipeline (writer) and apps/api (reader).

Tables:

* ``trades``: raw SDEX trades per tracked pair, deduplicated by Horizon id.
* ``ingest_runs``: one row per pair per ingest run (counts, newest trade, errors).
* ``market``: latest 24h market snapshot per pair (Horizon trade aggregations).
* ``score_runs`` / ``scores``: each scoring run and the per-wallet scores it
  produced. The API serves the latest *completed* run; earlier runs form
  each pair's score history.
* ``published_runs``: which runs were pushed to which on-chain registry.

SQLite in WAL mode lets the API read while the pipeline writes.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    pair TEXT NOT NULL,
    ledger_close_time TEXT NOT NULL,
    base_account TEXT NOT NULL,
    counter_account TEXT,
    base_asset TEXT NOT NULL,
    counter_asset TEXT NOT NULL,
    base_amount REAL NOT NULL,
    counter_amount REAL NOT NULL,
    price REAL NOT NULL,
    base_is_seller INTEGER NOT NULL,
    trade_type TEXT NOT NULL,
    liquidity_pool_id TEXT
);
CREATE INDEX IF NOT EXISTS trades_pair_time ON trades (pair, ledger_close_time);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    trades_fetched INTEGER NOT NULL DEFAULT 0,
    trades_inserted INTEGER NOT NULL DEFAULT 0,
    newest_trade_time TEXT,
    status TEXT NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS market (
    pair TEXT PRIMARY KEY,
    price REAL,
    change_24h_pct REAL,
    base_volume_24h REAL NOT NULL,
    counter_volume_24h REAL NOT NULL,
    trade_count_24h INTEGER NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS score_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    min_trades INTEGER NOT NULL,
    method TEXT NOT NULL,
    model_id TEXT,
    model_trained_on TEXT,
    data_as_of TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    run_id INTEGER NOT NULL REFERENCES score_runs (id),
    pair TEXT NOT NULL,
    wallet TEXT NOT NULL,
    score INTEGER NOT NULL,
    method TEXT NOT NULL,
    model_id TEXT,
    model_trained_on TEXT,
    benford_flag INTEGER NOT NULL,
    ml_flag INTEGER NOT NULL,
    confidence REAL NOT NULL,
    trade_count INTEGER NOT NULL,
    as_of TEXT NOT NULL,
    features TEXT NOT NULL,
    benford TEXT NOT NULL,
    shap TEXT,
    PRIMARY KEY (run_id, pair, wallet)
);
CREATE INDEX IF NOT EXISTS scores_run_pair ON scores (run_id, pair, score DESC);

CREATE TABLE IF NOT EXISTS published_runs (
    run_id INTEGER NOT NULL REFERENCES score_runs (id),
    contract_id TEXT NOT NULL,
    published_at TEXT NOT NULL,
    transactions INTEGER NOT NULL,
    PRIMARY KEY (run_id, contract_id)
);
"""


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _asset_symbol(asset: dict) -> str:
    return asset["code"] if asset.get("issuer") is None else f"{asset['code']}:{asset['issuer']}"


def _parse_asset(symbol: str) -> dict:
    if ":" in symbol:
        code, issuer = symbol.split(":", 1)
        return {"code": code, "issuer": issuer}
    return {"code": symbol, "issuer": None}


class Store:
    def __init__(self, path: str | Path, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        if not readonly:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if self.readonly:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=30)
        else:
            conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── trades ────────────────────────────────────────────────────────────────

    def insert_trades(self, pair: str, trades: pd.DataFrame) -> int:
        """Insert `trades` (a `load_historical_trades` DataFrame); returns new rows."""
        if trades.empty:
            return 0
        rows = [
            (
                str(t["id"]),
                pair,
                _iso(pd.Timestamp(t["ledger_close_time"]).to_pydatetime()),
                t["base_account"],
                t["counter_account"] if pd.notna(t["counter_account"]) else None,
                _asset_symbol(t["base_asset"]),
                _asset_symbol(t["counter_asset"]),
                float(t["base_amount"]),
                float(t["counter_amount"]),
                float(t["price"]),
                int(bool(t["base_is_seller"])),
                str(getattr(t["trade_type"], "value", t["trade_type"])),
                t.get("liquidity_pool_id") if pd.notna(t.get("liquidity_pool_id")) else None,
            )
            for t in trades.to_dict("records")
        ]
        with self.connect() as conn:
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
            )
            return conn.total_changes - before

    def newest_trade_time(self, pair: str) -> datetime | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT MAX(ledger_close_time) AS t FROM trades WHERE pair = ?", (pair,)
            ).fetchone()
        return _dt(row["t"])

    def trades_for_pair(self, pair: str, since: datetime | None = None) -> pd.DataFrame:
        """Trades on `pair` (optionally since a time) in `trades_to_frame` shape."""
        query = "SELECT * FROM trades WHERE pair = ?"
        params: list[Any] = [pair]
        if since is not None:
            query += " AND ledger_close_time >= ?"
            params.append(_iso(since))
        with self.connect() as conn:
            df = pd.read_sql_query(query + " ORDER BY ledger_close_time", conn, params=params)
        if df.empty:
            return df
        df["ledger_close_time"] = pd.to_datetime(df["ledger_close_time"], utc=True, format="ISO8601")
        df["base_asset"] = df["base_asset"].map(_parse_asset)
        df["counter_asset"] = df["counter_asset"].map(_parse_asset)
        df["base_is_seller"] = df["base_is_seller"].astype(bool)
        df["counter_account"] = df["counter_account"].where(df["counter_account"].notna(), None)
        return df

    def prune_trades(self, older_than: datetime) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM trades WHERE ledger_close_time < ?", (_iso(older_than),))
            return cur.rowcount

    # ── ingest runs / market ──────────────────────────────────────────────────

    def record_ingest(
        self,
        pair: str,
        started_at: datetime,
        fetched: int,
        inserted: int,
        status: str,
        error: str | None = None,
    ) -> None:
        newest = self.newest_trade_time(pair)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO ingest_runs (pair, started_at, finished_at, trades_fetched,"
                " trades_inserted, newest_trade_time, status, error) VALUES (?,?,?,?,?,?,?,?)",
                (
                    pair,
                    _iso(started_at),
                    _iso(datetime.now(timezone.utc)),
                    fetched,
                    inserted,
                    _iso(newest) if newest else None,
                    status,
                    error,
                ),
            )

    def save_market(self, pair: str, snapshot: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO market VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    pair,
                    snapshot["price"],
                    snapshot["change_24h_pct"],
                    snapshot["base_volume_24h"],
                    snapshot["counter_volume_24h"],
                    snapshot["trade_count_24h"],
                    _iso(snapshot["window_start"]),
                    _iso(snapshot["window_end"]),
                    _iso(datetime.now(timezone.utc)),
                ),
            )

    def market(self, pair: str | None = None) -> list[dict]:
        query, params = "SELECT * FROM market", ()
        if pair is not None:
            query, params = query + " WHERE pair = ?", (pair,)
        with self.connect() as conn:
            rows = [dict(r) for r in conn.execute(query, params)]
        for r in rows:
            for key in ("window_start", "window_end", "fetched_at"):
                r[key] = _dt(r[key])
        return rows

    def last_ingest(self) -> datetime | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT MAX(finished_at) AS t FROM ingest_runs WHERE status = 'ok'"
            ).fetchone()
        return _dt(row["t"])

    # ── scoring ───────────────────────────────────────────────────────────────

    def start_score_run(
        self,
        window_start: datetime,
        window_end: datetime,
        min_trades: int,
        method: str,
        model_id: str | None,
        model_trained_on: str | None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO score_runs (started_at, window_start, window_end, min_trades,"
                " method, model_id, model_trained_on, status) VALUES (?,?,?,?,?,?,?,'running')",
                (
                    _iso(datetime.now(timezone.utc)),
                    _iso(window_start),
                    _iso(window_end),
                    min_trades,
                    method,
                    model_id,
                    model_trained_on,
                ),
            )
            return int(cur.lastrowid)

    def save_scores(self, run_id: int, pair: str, results: list[dict]) -> None:
        rows = [
            (
                run_id,
                pair,
                r["wallet"],
                r["score"],
                r["method"],
                (r["model"] or {}).get("model_id"),
                (r["model"] or {}).get("trained_on"),
                int(r["benford_flag"]),
                int(r["ml_flag"]),
                r["confidence"],
                r["trade_count"],
                _iso(r["as_of"]),
                json.dumps(r["features"]),
                json.dumps(r["benford"]),
                json.dumps(r["shap"]) if r["shap"] is not None else None,
            )
            for r in results
        ]
        with self.connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
            )

    def finish_score_run(self, run_id: int, status: str, data_as_of: datetime | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE score_runs SET finished_at = ?, status = ?, data_as_of = ? WHERE id = ?",
                (
                    _iso(datetime.now(timezone.utc)),
                    status,
                    _iso(data_as_of) if data_as_of else None,
                    run_id,
                ),
            )

    def latest_score_run(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM score_runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        run = dict(row)
        for key in ("started_at", "finished_at", "window_start", "window_end", "data_as_of"):
            run[key] = _dt(run[key])
        return run

    def scores(self, run_id: int, pair: str | None = None, wallet: str | None = None) -> list[dict]:
        query, params = "SELECT * FROM scores WHERE run_id = ?", [run_id]
        if pair is not None:
            query += " AND pair = ?"
            params.append(pair)
        if wallet is not None:
            query += " AND wallet = ?"
            params.append(wallet)
        with self.connect() as conn:
            rows = [dict(r) for r in conn.execute(query + " ORDER BY score DESC", params)]
        return [self._decode_score(r) for r in rows]

    @staticmethod
    def _decode_score(r: dict) -> dict:
        return {
            "wallet": r["wallet"],
            "asset_pair": r["pair"],
            "score": r["score"],
            "method": r["method"],
            "model": (
                {"model_id": r["model_id"], "trained_on": r["model_trained_on"]}
                if r["model_id"]
                else None
            ),
            "benford_flag": bool(r["benford_flag"]),
            "ml_flag": bool(r["ml_flag"]),
            "confidence": r["confidence"],
            "trade_count": r["trade_count"],
            "timestamp": _dt(r["as_of"]),
            "features": json.loads(r["features"]),
            "benford": json.loads(r["benford"]),
            "shap": json.loads(r["shap"]) if r["shap"] else None,
        }

    def pairs_scored(self, run_id: int) -> list[str]:
        with self.connect() as conn:
            return [
                r["pair"]
                for r in conn.execute(
                    "SELECT DISTINCT pair FROM scores WHERE run_id = ? ORDER BY pair", (run_id,)
                )
            ]

    def pair_history(self, pair: str, limit: int = 200) -> list[dict]:
        """Average/max score for `pair` in each completed run, oldest first."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT r.window_end AS t, AVG(s.score) AS avg_score, MAX(s.score) AS max_score"
                " FROM scores s JOIN score_runs r ON r.id = s.run_id"
                " WHERE s.pair = ? AND r.status = 'ok'"
                " GROUP BY r.id ORDER BY r.id DESC LIMIT ?",
                (pair, limit),
            ).fetchall()
        return [
            {
                "timestamp": _dt(r["t"]),
                "average_score": round(r["avg_score"], 2),
                "max_score": r["max_score"],
            }
            for r in reversed(rows)
        ]

    # ── on-chain publishing ───────────────────────────────────────────────────

    def was_published(self, run_id: int, contract_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM published_runs WHERE run_id = ? AND contract_id = ?",
                (run_id, contract_id),
            ).fetchone()
        return row is not None

    def mark_published(self, run_id: int, contract_id: str, transactions: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO published_runs VALUES (?,?,?,?)",
                (run_id, contract_id, _iso(datetime.now(timezone.utc)), transactions),
            )
