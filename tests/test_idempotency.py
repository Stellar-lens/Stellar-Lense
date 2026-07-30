"""Tests for pipeline/idempotency.py (Issue #435).

Covers:
- CheckpointStore: make_run_id, mark_started/done/failed, is_complete, TTL
- PipelineCheckpoint context manager: skip path, execute path, failure path
- idempotent_upsert: skips write when content is unchanged
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from pipeline.idempotency import (
    PIPELINE_STAGES,
    CheckpointStore,
    PipelineCheckpoint,
    _risk_score_hash,
    idempotent_upsert,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path):
    """In-memory SQLite checkpoint store for test isolation."""
    return CheckpointStore(db_url="sqlite:///:memory:")


@pytest.fixture()
def pair_id():
    return "USDC:GA5Z.../XLM:native"


@pytest.fixture()
def run_id(pair_id):
    return CheckpointStore.make_run_id(pair_id, "2024-01-01")


# ---------------------------------------------------------------------------
# CheckpointStore
# ---------------------------------------------------------------------------


class TestCheckpointStore:
    def test_make_run_id_is_deterministic(self, pair_id):
        a = CheckpointStore.make_run_id(pair_id, "2024-01-01")
        b = CheckpointStore.make_run_id(pair_id, "2024-01-01")
        assert a == b

    def test_make_run_id_differs_on_different_inputs(self, pair_id):
        a = CheckpointStore.make_run_id(pair_id, "2024-01-01")
        b = CheckpointStore.make_run_id(pair_id, "2024-01-02")
        assert a != b

    def test_make_run_id_is_16_chars(self, pair_id):
        run_id = CheckpointStore.make_run_id(pair_id, "2024")
        assert len(run_id) == 16

    def test_stage_not_complete_before_any_write(self, store, run_id, pair_id):
        assert store.is_complete(run_id, pair_id, "ingest") is False

    def test_mark_done_makes_stage_complete(self, store, run_id, pair_id):
        store.mark_started(run_id, pair_id, "ingest")
        store.mark_done(run_id, pair_id, "ingest")
        assert store.is_complete(run_id, pair_id, "ingest") is True

    def test_mark_failed_stage_is_not_complete(self, store, run_id, pair_id):
        store.mark_started(run_id, pair_id, "ingest")
        store.mark_failed(run_id, pair_id, "ingest", error="timeout")
        assert store.is_complete(run_id, pair_id, "ingest") is False

    def test_get_result_returns_stored_payload(self, store, run_id, pair_id):
        store.mark_done(run_id, pair_id, "scoring", result={"score": 42})
        result = store.get_result(run_id, pair_id, "scoring")
        assert result == {"score": 42}

    def test_get_result_returns_none_for_unknown(self, store, run_id, pair_id):
        assert store.get_result(run_id, pair_id, "scoring") is None

    def test_mark_done_twice_updates_record(self, store, run_id, pair_id):
        store.mark_done(run_id, pair_id, "ingest", result={"rows": 10})
        store.mark_done(run_id, pair_id, "ingest", result={"rows": 20})
        result = store.get_result(run_id, pair_id, "ingest")
        assert result["rows"] == 20

    def test_list_stages_empty_before_any_write(self, store, run_id, pair_id):
        assert store.list_stages(run_id, pair_id) == []

    def test_list_stages_returns_all_started_stages(self, store, run_id, pair_id):
        store.mark_started(run_id, pair_id, "ingest")
        store.mark_started(run_id, pair_id, "features")
        stages = {r.stage for r in store.list_stages(run_id, pair_id)}
        assert stages == {"ingest", "features"}

    def test_first_incomplete_stage_returns_none_when_all_done(self, store, run_id, pair_id):
        for s in PIPELINE_STAGES:
            store.mark_done(run_id, pair_id, s)
        assert store.first_incomplete_stage(run_id, pair_id) is None

    def test_first_incomplete_stage_skips_completed(self, store, run_id, pair_id):
        store.mark_done(run_id, pair_id, "ingest")
        store.mark_done(run_id, pair_id, "orderbook")
        first = store.first_incomplete_stage(run_id, pair_id)
        assert first == "funding_graph"

    def test_ttl_expired_checkpoint_is_not_complete(self, tmp_path, pair_id):
        """A checkpoint completed before the TTL window is treated as stale."""
        # Use TTL of 0 hours — any completed checkpoint is instantly stale.
        store = CheckpointStore(db_url="sqlite:///:memory:", ttl_hours=0)
        run_id = CheckpointStore.make_run_id(pair_id, "ttl-test")
        store.mark_done(run_id, pair_id, "ingest")
        # With ttl_hours=0 the record is immediately stale.
        assert store.is_complete(run_id, pair_id, "ingest") is False

    def test_purge_old_checkpoints_removes_stale_rows(self, pair_id):
        store = CheckpointStore(db_url="sqlite:///:memory:", ttl_hours=0)
        run_id = CheckpointStore.make_run_id(pair_id, "purge-test")
        store.mark_done(run_id, pair_id, "ingest")
        deleted = store.purge_old_checkpoints(older_than_hours=0)
        assert deleted >= 1
        assert store.list_stages(run_id, pair_id) == []

    def test_different_pairs_are_isolated(self, store, run_id):
        store.mark_done(run_id, "PAIR_A", "ingest")
        assert store.is_complete(run_id, "PAIR_A", "ingest") is True
        assert store.is_complete(run_id, "PAIR_B", "ingest") is False

    def test_different_run_ids_are_isolated(self, store, pair_id):
        run_a = CheckpointStore.make_run_id(pair_id, "run-a")
        run_b = CheckpointStore.make_run_id(pair_id, "run-b")
        store.mark_done(run_a, pair_id, "ingest")
        assert store.is_complete(run_a, pair_id, "ingest") is True
        assert store.is_complete(run_b, pair_id, "ingest") is False


# ---------------------------------------------------------------------------
# PipelineCheckpoint context manager
# ---------------------------------------------------------------------------


class TestPipelineCheckpoint:
    def test_skip_false_on_first_run(self, store, run_id, pair_id):
        with PipelineCheckpoint(store, run_id, pair_id, "ingest") as cp:
            assert cp.skip is False

    def test_stage_marked_done_on_clean_exit(self, store, run_id, pair_id):
        with PipelineCheckpoint(store, run_id, pair_id, "ingest"):
            pass
        assert store.is_complete(run_id, pair_id, "ingest") is True

    def test_stage_marked_failed_on_exception(self, store, run_id, pair_id):
        with pytest.raises(ValueError):
            with PipelineCheckpoint(store, run_id, pair_id, "ingest"):
                raise ValueError("oh no")
        assert store.is_complete(run_id, pair_id, "ingest") is False
        records = store.list_stages(run_id, pair_id)
        assert any(r.status == "failed" for r in records)

    def test_skip_true_on_second_run(self, store, run_id, pair_id):
        with PipelineCheckpoint(store, run_id, pair_id, "ingest"):
            pass
        with PipelineCheckpoint(store, run_id, pair_id, "ingest") as cp:
            assert cp.skip is True

    def test_result_available_on_skip(self, store, run_id, pair_id):
        with PipelineCheckpoint(store, run_id, pair_id, "scoring") as cp:
            cp.set_result({"wallet_count": 50})
        with PipelineCheckpoint(store, run_id, pair_id, "scoring") as cp:
            assert cp.skip is True
            assert cp.result == {"wallet_count": 50}

    def test_force_reruns_completed_stage(self, store, run_id, pair_id):
        executed = []
        with PipelineCheckpoint(store, run_id, pair_id, "ingest"):
            executed.append("first")
        with PipelineCheckpoint(store, run_id, pair_id, "ingest", force=True) as cp:
            assert cp.skip is False
            executed.append("second")
        assert executed == ["first", "second"]

    def test_exception_propagates(self, store, run_id, pair_id):
        with pytest.raises(RuntimeError, match="pipeline error"):
            with PipelineCheckpoint(store, run_id, pair_id, "features"):
                raise RuntimeError("pipeline error")

    def test_result_not_persisted_on_failure(self, store, run_id, pair_id):
        with pytest.raises(ValueError):
            with PipelineCheckpoint(store, run_id, pair_id, "scoring") as cp:
                cp.set_result({"score": 99})
                raise ValueError("scoring crashed")
        assert store.get_result(run_id, pair_id, "scoring") is None


# ---------------------------------------------------------------------------
# idempotent_upsert
# ---------------------------------------------------------------------------


class TestIdempotentUpsert:
    def _make_store_mock(self, existing_score: dict | None):
        """Build a mock RiskScoreStore where .get() returns a fake record."""
        mock_store = MagicMock()
        if existing_score is None:
            mock_store.get.return_value = None
        else:
            record = MagicMock()
            record.score = existing_score["score"]
            record.benford_flag = existing_score["benford_flag"]
            record.ml_flag = existing_score["ml_flag"]
            record.confidence = existing_score["confidence"]
            record.ring_id = existing_score.get("ring_id")
            mock_store.get.return_value = record
            mock_store.upsert.return_value = record
        return mock_store

    def test_write_on_first_insert(self):
        mock = self._make_store_mock(None)
        score = {"score": 80, "benford_flag": True, "ml_flag": True, "confidence": 90}
        was_written, _ = idempotent_upsert(mock, "WALLET_A", "USDC/XLM", score)
        assert was_written is True
        mock.upsert.assert_called_once()

    def test_no_write_when_score_unchanged(self):
        score = {"score": 80, "benford_flag": True, "ml_flag": True, "confidence": 90}
        mock = self._make_store_mock(score)
        was_written, _ = idempotent_upsert(mock, "WALLET_A", "USDC/XLM", score)
        assert was_written is False
        mock.upsert.assert_not_called()

    def test_write_when_score_changes(self):
        existing = {"score": 80, "benford_flag": True, "ml_flag": True, "confidence": 90}
        incoming = {"score": 85, "benford_flag": True, "ml_flag": True, "confidence": 90}
        mock = self._make_store_mock(existing)
        was_written, _ = idempotent_upsert(mock, "WALLET_A", "USDC/XLM", incoming)
        assert was_written is True
        mock.upsert.assert_called_once()

    def test_write_when_flag_changes(self):
        existing = {"score": 80, "benford_flag": False, "ml_flag": True, "confidence": 90}
        incoming = {"score": 80, "benford_flag": True, "ml_flag": True, "confidence": 90}
        mock = self._make_store_mock(existing)
        was_written, _ = idempotent_upsert(mock, "WALLET_A", "USDC/XLM", incoming)
        assert was_written is True

    def test_ring_id_included_in_hash(self):
        base = {"score": 50, "benford_flag": False, "ml_flag": False, "confidence": 60}
        with_ring = dict(base, ring_id="ring_abc123")
        h1 = _risk_score_hash(base)
        h2 = _risk_score_hash(with_ring)
        assert h1 != h2

    def test_hash_is_stable_across_calls(self):
        score = {"score": 50, "benford_flag": True, "ml_flag": False, "confidence": 70}
        assert _risk_score_hash(score) == _risk_score_hash(score)

    def test_no_write_when_ring_id_unchanged(self):
        score = {
            "score": 70,
            "benford_flag": True,
            "ml_flag": False,
            "confidence": 80,
            "ring_id": "ring_xyz",
        }
        mock = self._make_store_mock(score)
        was_written, _ = idempotent_upsert(mock, "WALLET_B", "USDC/XLM", score)
        assert was_written is False

    def test_write_when_ring_id_changes(self):
        existing = {
            "score": 70,
            "benford_flag": True,
            "ml_flag": False,
            "confidence": 80,
            "ring_id": "ring_old",
        }
        incoming = dict(existing, ring_id="ring_new")
        mock = self._make_store_mock(existing)
        was_written, _ = idempotent_upsert(mock, "WALLET_B", "USDC/XLM", incoming)
        assert was_written is True
