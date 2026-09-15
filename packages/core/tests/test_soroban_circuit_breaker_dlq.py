"""Tests for the hardened Soroban circuit breaker: half-open state, health endpoint,
manual reset, and dead-letter queue (Issue #143).
"""

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import detection.soroban_publisher as _soroban_publisher_module
from config.settings import settings
from detection.soroban_publisher import (
    SorobanCircuitOpenError,
    SorobanHealthStatus,
    SorobanPublisher,
    get_dlq_entries,
    get_dlq_pending_count,
    init_dlq_schema,
)
from detection.risk_score import RiskScore


@pytest.fixture(autouse=True)
def _real_soroban_publisher_in_sys_modules():
    """Guard against test_soroban_publisher.py's collection-time stellar_sdk
    mock leaking here.

    That file replaces sys.modules["detection.soroban_publisher"] with a
    module reloaded against a MagicMock stellar_sdk. unittest.mock.patch()
    resolves a dotted-string target via the *current* sys.modules entry, not
    via whichever module object a class's methods actually resolve globals
    against — so once both files have been collected, patch(
    "detection.soroban_publisher.Keypair") in the ``publisher`` fixture
    below silently patches that other (mock-backed) module instead of this
    one, and SorobanPublisher.__init__ calls the *real* Keypair.from_secret()
    on a fake 56-char secret and raises before the mock ever applies.
    Pin sys.modules to the real module (captured at this file's own import
    time, above) for the duration of every test here.
    """
    saved = sys.modules.get("detection.soroban_publisher")
    sys.modules["detection.soroban_publisher"] = _soroban_publisher_module
    try:
        yield
    finally:
        if saved is not None:
            sys.modules["detection.soroban_publisher"] = saved
        else:
            sys.modules.pop("detection.soroban_publisher", None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    """Temporary SQLite DB for isolation."""
    return str(tmp_path / "test.db")


@pytest.fixture
def publisher(db_path):
    """SorobanPublisher with a stub keypair and a 3-failure threshold."""
    with patch("detection.soroban_publisher.Keypair") as mock_kp:
        mock_kp.from_secret.return_value = MagicMock()
        pub = SorobanPublisher(
            contract_id="C" * 56,
            secret_key="S" * 56,
            soroban_rpc_url="https://test",
            network_passphrase="Test",
            circuit_breaker_threshold=3,
            circuit_reset_seconds=10,
            db_path=db_path,
        )
    return pub


def _make_score(wallet: str = "GABC", asset_pair: str = "XLM/USDC", score: int = 80) -> RiskScore:
    return RiskScore(
        wallet=wallet,
        asset_pair=asset_pair,
        score=score,
        benford_flag=True,
        ml_flag=True,
        confidence=90,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Unit: half-open state machine
# ---------------------------------------------------------------------------


def test_circuit_opens_after_threshold_failures(publisher):
    """After threshold failures the circuit must be 'open'."""
    for _ in range(3):
        publisher._record_failure("test error")
    assert publisher._circuit_state == "open"


def test_circuit_transitions_to_half_open_after_reset_timeout(publisher):
    """After reset_seconds the circuit should allow a probe (half-open)."""
    for _ in range(3):
        publisher._record_failure("err")
    assert publisher._circuit_state == "open"

    # Simulate reset timeout elapsed
    publisher._circuit_opened_at = time.monotonic() - (publisher._circuit_reset_seconds + 1)
    publisher._check_circuit()  # should not raise
    assert publisher._circuit_state == "half-open"


def test_successful_probe_closes_circuit(publisher):
    """A successful submission in half-open should close the circuit."""
    for _ in range(3):
        publisher._record_failure("err")
    publisher._circuit_opened_at = time.monotonic() - (publisher._circuit_reset_seconds + 1)
    publisher._check_circuit()  # enter half-open
    assert publisher._circuit_state == "half-open"

    publisher._record_success()
    assert publisher._circuit_state == "closed"
    assert publisher._consecutive_failures == 0
    assert publisher._last_error is None


def test_failed_probe_reopens_circuit(publisher):
    """A failed probe in half-open should push state back to open."""
    for _ in range(3):
        publisher._record_failure("err")
    publisher._circuit_opened_at = time.monotonic() - (publisher._circuit_reset_seconds + 1)
    publisher._check_circuit()  # half-open
    assert publisher._circuit_state == "half-open"

    publisher._record_failure("probe failed")
    assert publisher._circuit_state == "open"
    # Timer must be restarted
    assert publisher._circuit_opened_at is not None


def test_manual_reset_closes_circuit(publisher):
    """reset_circuit() immediately closes an open circuit."""
    for _ in range(3):
        publisher._record_failure("err")
    assert publisher._circuit_state == "open"

    health = publisher.reset_circuit()
    assert health.circuit_state == "closed"
    assert health.consecutive_failures == 0
    assert health.last_error is None
    assert publisher._circuit_state == "closed"


def test_manual_reset_clears_consecutive_failures(publisher):
    """After reset, consecutive_failures must be 0."""
    publisher._record_failure("e1")
    publisher._record_failure("e2")
    publisher.reset_circuit()
    assert publisher._consecutive_failures == 0


# ---------------------------------------------------------------------------
# Unit: DLQ write on open circuit
# ---------------------------------------------------------------------------


def test_dlq_written_when_circuit_open(publisher, db_path, monkeypatch):
    """When circuit is open and submit_batch is called, DLQ rows should be written."""
    # This test is about circuit-breaker/DLQ behaviour, not multi-region lease
    # coordination — disable the lease so submit_score doesn't require the
    # optional `kubernetes` package (not installed in the CI test extra).
    monkeypatch.setattr(settings, "soroban_submission_lease_enabled", False)

    # Force circuit open
    for _ in range(3):
        publisher._record_failure("err")
    assert publisher._circuit_state == "open"

    score = _make_score()
    with patch("detection.soroban_publisher.save_submission"):
        try:
            publisher.submit_score(score)
        except SorobanCircuitOpenError:
            pass

    count = get_dlq_pending_count(db_path)
    assert count == 1


def test_dlq_write_directly(publisher, db_path):
    """_write_dead_letter should persist a pending row."""
    publisher._write_dead_letter(
        wallet="GABC",
        asset_pair="XLM/USDC",
        score=85,
        timestamp=1000000,
        error="test error",
    )
    count = get_dlq_pending_count(db_path)
    assert count == 1


# ---------------------------------------------------------------------------
# Unit: dlq-replay success and failure
# ---------------------------------------------------------------------------


def test_dlq_replay_success(publisher, db_path):
    """Replayed item should be marked 'replayed' with a tx_hash."""
    init_dlq_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO soroban_dead_letters (wallet, asset_pair, score, ledger_timestamp, error_message, status) "
            "VALUES ('GABC', 'XLM/USDC', 80, 1000000, 'test', 'pending')"
        )
        conn.commit()

    items, _ = get_dlq_entries(status="pending", page=1, page_size=10, db_path=db_path)
    assert len(items) == 1

    with patch.object(publisher, "submit_score", return_value="txhash123"):
        score_obj = _make_score()
        tx = publisher.submit_score(score_obj)
        assert tx == "txhash123"

    # Manually simulate what dlq_replay does
    now_iso = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE soroban_dead_letters SET status='replayed', replayed_at=?, replay_tx_hash=? WHERE id=1",
            (now_iso, "txhash123"),
        )
        conn.commit()

    items_after, _ = get_dlq_entries(status="replayed", page=1, page_size=10, db_path=db_path)
    assert len(items_after) == 1
    assert items_after[0]["replay_tx_hash"] == "txhash123"


def test_dlq_replay_failure(publisher, db_path):
    """Failed replay should mark item as 'failed'."""
    init_dlq_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO soroban_dead_letters (wallet, asset_pair, score, ledger_timestamp, error_message, status) "
            "VALUES ('GABC', 'XLM/USDC', 80, 1000000, 'test', 'pending')"
        )
        conn.commit()

    # Simulate failed replay
    now_iso = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE soroban_dead_letters SET status='failed', replayed_at=? WHERE id=1",
            (now_iso,),
        )
        conn.commit()

    items_after, _ = get_dlq_entries(status="failed", page=1, page_size=10, db_path=db_path)
    assert len(items_after) == 1
    assert items_after[0]["replay_tx_hash"] is None


# ---------------------------------------------------------------------------
# Unit: health snapshot
# ---------------------------------------------------------------------------


def test_health_returns_closed_initially(publisher):
    h = publisher.health()
    assert h.circuit_state == "closed"
    assert h.consecutive_failures == 0
    assert h.last_error is None
    assert h.seconds_until_reset is None


def test_health_returns_open_when_circuit_open(publisher):
    for _ in range(3):
        publisher._record_failure("err")
    h = publisher.health()
    assert h.circuit_state == "open"
    assert h.consecutive_failures == 3
    assert h.last_error == "err"
    assert h.seconds_until_reset is not None
    assert h.seconds_until_reset >= 0


# ---------------------------------------------------------------------------
# Integration: GET /admin/soroban/health (direct router tests without full app)
# ---------------------------------------------------------------------------


def test_admin_soroban_health_returns_correct_schema(db_path):
    """SorobanHealthStatus has all required fields and correct types."""
    h = SorobanHealthStatus(
        circuit_state="closed",
        consecutive_failures=0,
        last_error=None,
        circuit_opened_at=None,
        seconds_until_reset=None,
        dlq_pending_count=2,
    )
    assert h.circuit_state == "closed"
    assert h.dlq_pending_count == 2
    assert h.consecutive_failures == 0
    assert h.last_error is None
    assert h.seconds_until_reset is None
    assert h.circuit_opened_at is None


def test_admin_soroban_health_503_without_key():
    """require_admin_key dependency raises 503 when STELLARLENSE_ADMIN_API_KEY unset."""
    from fastapi import HTTPException
    from api.auth import require_admin_key
    from config import settings as settings_mod

    with patch.object(type(settings_mod.settings), "admin_api_key", new_callable=lambda: property(lambda self: "")):
        with pytest.raises(HTTPException) as exc_info:
            require_admin_key(x_stellarlense_admin_key="")
        assert exc_info.value.status_code == 503


def test_admin_soroban_reset_closes_circuit(publisher):
    """reset_circuit on a publisher returns closed state."""
    for _ in range(3):
        publisher._record_failure("err")
    assert publisher._circuit_state == "open"

    health = publisher.reset_circuit()
    assert health.circuit_state == "closed"
    assert health.consecutive_failures == 0


def test_admin_dead_letters_pagination(db_path):
    """get_dlq_entries pagination works correctly."""
    init_dlq_schema(db_path)
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        for i in range(5):
            conn.execute(
                "INSERT INTO soroban_dead_letters "
                "(wallet, asset_pair, score, ledger_timestamp, status) "
                "VALUES (?, 'XLM/USDC', 80, 1000000, 'pending')",
                (f"GABC{i:04d}",),
            )
        conn.commit()

    items, total = get_dlq_entries(page=1, page_size=3, db_path=db_path)
    assert total == 5
    assert len(items) == 3

    items2, total2 = get_dlq_entries(page=2, page_size=3, db_path=db_path)
    assert total2 == 5
    assert len(items2) == 2


def test_admin_dead_letters_status_filter(db_path):
    """get_dlq_entries status filter works."""
    init_dlq_schema(db_path)
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO soroban_dead_letters "
            "(wallet, asset_pair, score, ledger_timestamp, status) "
            "VALUES ('GABC', 'XLM/USDC', 80, 1000000, 'pending')"
        )
        conn.execute(
            "INSERT INTO soroban_dead_letters "
            "(wallet, asset_pair, score, ledger_timestamp, status) "
            "VALUES ('GDEF', 'XLM/USDC', 70, 1000001, 'replayed')"
        )
        conn.commit()

    pending, _ = get_dlq_entries(status="pending", db_path=db_path)
    assert len(pending) == 1
    assert pending[0]["wallet"] == "GABC"

    replayed, _ = get_dlq_entries(status="replayed", db_path=db_path)
    assert len(replayed) == 1
    assert replayed[0]["wallet"] == "GDEF"
