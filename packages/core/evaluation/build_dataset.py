"""Build the small labelled evaluation set from a pipeline store + Horizon.

Labels come from *fund flows between accounts*, signals the scorer does not
use. For each sampled wallet W and its largest counterparty C (by volume):

    positive (1): a funding link exists:
                  - W and C were created by the same account, or one created
                    the other ("creator" = funder of the account's
                    `create_account` operation); or
                  - W and C sent each other funds directly (any payment,
                    path payment, create_account or merge between them in
                    either account's retained payment history).
                  Moving money straight between two trading accounts is a
                  common sign that one operator controls both sides.
    negative (0): no link found, and the check was complete: both creators
                  are known, or both accounts' retained payment histories
                  were scanned to the end (<= MAX_PAYMENT_PAGES pages).
    unknown:      no link found but the check was incomplete (account older
                  than public Horizon's ~1 year of retained history, or a
                  payment history too long to scan). Written to the CSV,
                  excluded from metrics.

These are proxy labels, not confirmed cases: an exchange that funds or pays
many unrelated users can make two of them look linked, and a wash trader
who keeps the two accounts' funding fully separate looks clean. REPORT.md
states this next to the numbers.

Outputs (committed, so `evaluate.py` runs offline and reproducibly):

    data/labelled_wallets.csv   one row per sampled wallet, with the evidence
    data/trades.csv.gz          every stored trade involving a sampled wallet

Usage (needs network, read-only Horizon GETs):

    uv run --package stellar-lense-core python packages/core/evaluation/build_dataset.py \
        --db data/stellar_lense.db --sample 150
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.store import Store  # noqa: E402

HORIZON = "https://horizon.stellar.org"
MAX_PAYMENT_PAGES = 5  # x 200 records
DATA = Path(__file__).with_name("data")


def creator_of(client: httpx.Client, account: str, cache: dict[str, str | None]) -> str | None:
    if account in cache:
        return cache[account]
    time.sleep(0.15)  # stay well under public Horizon's rate limit
    response = client.get(
        f"{HORIZON}/accounts/{account}/operations", params={"order": "asc", "limit": 1}
    )
    creator = None
    if response.status_code == 200:
        records = response.json()["_embedded"]["records"]
        if records and records[0]["type"] == "create_account" and records[0]["account"] == account:
            creator = records[0]["funder"]
    cache[account] = creator
    return creator


def payment_partners(client: httpx.Client, account: str, cache: dict) -> tuple[set[str], bool]:
    """Accounts `account` sent funds to or received funds from, and whether
    the whole retained history was scanned."""
    if account in cache:
        return cache[account]
    partners: set[str] = set()
    url: str | None = f"{HORIZON}/accounts/{account}/payments"
    params: dict | None = {"order": "desc", "limit": 200}
    complete = False
    for _ in range(MAX_PAYMENT_PAGES):
        time.sleep(0.15)
        response = client.get(url, params=params)
        if response.status_code != 200:
            break
        page = response.json()
        records = page["_embedded"]["records"]
        for r in records:
            for key in ("from", "to", "funder", "account", "into"):
                if r.get(key) and r[key] != account:
                    partners.add(r[key])
        if len(records) < 200:
            complete = True
            break
        url, params = page["_links"]["next"]["href"], None
    cache[account] = (partners, complete)
    return cache[account]


def top_counterparty(trades: pd.DataFrame, wallet: str) -> tuple[str | None, float]:
    own = trades[(trades["base_account"] == wallet) | (trades["counter_account"] == wallet)]
    cp = own.apply(
        lambda r: r["counter_account"] if r["base_account"] == wallet else r["base_account"], axis=1
    ).dropna()
    if cp.empty:
        return None, 0.0
    volume = own.loc[cp.index, "base_amount"].groupby(cp).sum()
    return volume.idxmax(), float(volume.max() / volume.sum())


def label(
    wallet: str,
    cp: str | None,
    w_creator: str | None,
    cp_creator: str | None,
    w_partners: tuple[set[str], bool],
    cp_partners: tuple[set[str], bool],
) -> tuple[str, str]:
    if cp is None:
        return "unknown", "no wallet counterparty (pool trades only)"
    if w_creator and w_creator == cp_creator:
        return "1", "same creator"
    if w_creator == cp or cp_creator == wallet:
        return "1", "one account created the other"
    if cp in w_partners[0] or wallet in cp_partners[0]:
        return "1", "direct payments between them"
    if w_creator and cp_creator:
        return "0", "no link (creators known)"
    if w_partners[1] and cp_partners[1]:
        return "0", "no link (full payment histories scanned)"
    return "unknown", "no link found, check incomplete"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--sample", type=int, default=150)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    store = Store(args.db, readonly=True)
    run = store.latest_score_run()
    if run is None:
        raise SystemExit("no completed score run in that database")
    scored = [(s["asset_pair"], s["wallet"], s["score"]) for s in store.scores(run["id"])]

    # Every wallet scoring >= 40 plus a seeded random sample of the rest, so
    # the set contains enough high scores to measure precision at all.
    rng = random.Random(args.seed)
    high = [s for s in scored if s[2] >= 40]
    rest = [s for s in scored if s[2] < 40]
    sample = high + rng.sample(rest, max(0, min(len(rest), args.sample - len(high))))

    DATA.mkdir(exist_ok=True)
    trades_by_pair = {pair: store.trades_for_pair(pair) for pair in {p for p, _, _ in sample}}
    cache: dict[str, str | None] = {}
    pay_cache: dict = {}
    rows, trade_frames = [], []
    with httpx.Client(timeout=30.0) as client:
        for i, (pair, wallet, _score) in enumerate(sample, 1):
            trades = trades_by_pair[pair]
            own = trades[(trades["base_account"] == wallet) | (trades["counter_account"] == wallet)]
            trade_frames.append(own.assign(pair=pair))
            cp, cp_share = top_counterparty(trades, wallet)
            w_creator = creator_of(client, wallet, cache)
            cp_creator = creator_of(client, cp, cache) if cp else None
            w_pay = payment_partners(client, wallet, pay_cache)
            cp_pay = payment_partners(client, cp, pay_cache) if cp else (set(), False)
            lab, why = label(wallet, cp, w_creator, cp_creator, w_pay, cp_pay)
            rows.append(
                {
                    "pair": pair,
                    "wallet": wallet,
                    "top_counterparty": cp or "",
                    "top_counterparty_volume_share": round(cp_share, 4),
                    "wallet_creator": w_creator or "",
                    "counterparty_creator": cp_creator or "",
                    "label": lab,
                    "label_reason": why,
                }
            )
            if i % 25 == 0:
                print(f"{i}/{len(sample)} labelled", file=sys.stderr)

    with open(DATA / "labelled_wallets.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    trades = pd.concat(trade_frames).drop_duplicates(subset=["id", "pair"])
    trades["base_asset"] = trades["base_asset"].map(lambda a: a["code"] + (f":{a['issuer']}" if a["issuer"] else ""))
    trades["counter_asset"] = trades["counter_asset"].map(lambda a: a["code"] + (f":{a['issuer']}" if a["issuer"] else ""))
    trades.to_csv(DATA / "trades.csv.gz", index=False)

    meta = DATA / "SOURCE.txt"
    meta.write_text(
        f"built {datetime.now(timezone.utc).isoformat()} from score run {run['id']} "
        f"(window {run['window_start']} .. {run['window_end']}), "
        f"{len(rows)} wallets, {len(trades)} trades, seed {args.seed}\n"
    )
    counts = pd.Series([r["label"] for r in rows]).value_counts().to_dict()
    print(f"wrote {len(rows)} wallets {counts} and {len(trades)} trades to {DATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
