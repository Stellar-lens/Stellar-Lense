from datetime import datetime, timedelta, timezone

from pipeline.jobs import Pair, PairConfig, ingest, score
from pipeline.publish import plan, publish
from pipeline.store import Store
from tests.fake_horizon import USDC_ISSUER, FakeHorizon, wash_and_organic

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
PAIR = Pair("XLM", f"USDC:{USDC_ISSUER}")
CONFIG = PairConfig("https://horizon.test", "mainnet", [PAIR])


class FakeRegistry:
    contract_id = "CFAKE"

    def __init__(self):
        self.pairs, self.batches = [], []

    def submit_pair_score(self, signer, pair, average, max_, flagged, total, as_of):
        self.pairs.append((pair, average, max_, flagged, total, as_of))
        return "tx"

    def submit_scores(self, signer, rows):
        self.batches.append(rows)
        return "tx"


def _scored_store(tmp_path) -> Store:
    store = Store(tmp_path / "db.sqlite")
    ingest(store, CONFIG, client=FakeHorizon(wash_and_organic(NOW)).client(), now=NOW)
    score(store, CONFIG, now=NOW)
    return store


def test_plan_lists_aggregate_and_top_wallets(tmp_path):
    work = plan(_scored_store(tmp_path), top_k=2)
    (p,) = work["pairs"]
    assert p["pair"] == PAIR.id
    assert p["aggregate"]["total"] == 3
    assert p["aggregate"]["average"] <= p["aggregate"]["max"]
    assert [w["wallet"] for w in p["wallets"]][0] in ("GWASHA", "GWASHB")
    assert len(p["wallets"]) == 2
    assert all(isinstance(w["as_of"], int) for w in p["wallets"])


def test_publish_once_per_run(tmp_path):
    store = _scored_store(tmp_path)
    registry = FakeRegistry()
    first = publish(store, registry, signer=None, top_k=10, batch_size=2)
    assert first["status"] == "published"
    assert len(registry.pairs) == 1
    assert [len(b) for b in registry.batches] == [2, 1]  # 3 wallets, batches of 2
    assert first["transactions"] == 3

    again = publish(store, registry, signer=None)
    assert again == {"status": "already_published", "run_id": first["run_id"]}
    assert len(registry.pairs) == 1

    # A new scoring run gets published.
    score(store, CONFIG, now=NOW + timedelta(minutes=15))
    assert publish(store, registry, signer=None)["status"] == "published"


def test_publish_without_runs(tmp_path):
    assert publish(Store(tmp_path / "empty.db"), FakeRegistry(), signer=None) == {
        "status": "nothing_scored"
    }
