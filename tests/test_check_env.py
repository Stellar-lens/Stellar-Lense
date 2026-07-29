"""Tests for scripts/check_env.py, the `make check-env` dev command."""

import json

import pytest

from config import Config
from scripts import check_env


def test_single_passing_mode_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(Config, "RISK_SCORE_DB_URL", "sqlite:///test.db")
    monkeypatch.setattr(Config, "MODEL_DIR", "./models")
    monkeypatch.setattr(Config, "API_KEYS", ["$2b$somehash"])
    monkeypatch.setattr(Config, "API_RATE_LIMIT_RPM", 60)

    code = check_env.main(["--mode", "api"])

    assert code == 0
    assert "[OK]   api" in capsys.readouterr().out


def test_single_failing_mode_exits_nonzero_and_prints_reason(monkeypatch, capsys):
    monkeypatch.setattr(Config, "RISK_SCORE_DB_URL", "sqlite:///test.db")
    monkeypatch.setattr(Config, "MODEL_DIR", "./models")
    monkeypatch.setattr(Config, "API_KEYS", [])
    monkeypatch.setattr(Config, "API_RATE_LIMIT_RPM", 60)

    code = check_env.main(["--mode", "api"])

    out = capsys.readouterr().out
    assert code == 1
    assert "[FAIL] api" in out
    assert "API_KEYS" in out


def test_all_flag_checks_every_registered_mode(monkeypatch, capsys):
    monkeypatch.setattr(Config, "WATCHED_ASSET_PAIRS", [("USDC", "native")])
    monkeypatch.setattr(Config, "RISK_SCORE_DB_URL", "sqlite:///test.db")
    monkeypatch.setattr(Config, "MODEL_DIR", "./models")

    code = check_env.main(["--all"])

    out = capsys.readouterr().out
    for mode in ("pipeline", "api", "streaming_sse", "streaming_kafka", "ws_server", "training"):
        assert mode in out
    assert code == 1  # onchain/ws_server modes are unconfigured in this test


def test_json_output_is_valid_and_matches_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(Config, "RISK_SCORE_DB_URL", "sqlite:///test.db")
    monkeypatch.setattr(Config, "MODEL_DIR", "./models")
    monkeypatch.setattr(Config, "API_KEYS", ["$2b$somehash"])
    monkeypatch.setattr(Config, "API_RATE_LIMIT_RPM", 60)

    code = check_env.main(["--mode", "api", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["results"] == [{"mode": "api", "ok": True, "error": None}]


def test_mode_and_all_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        check_env.main(["--mode", "api", "--all"])


def test_requires_mode_or_all():
    with pytest.raises(SystemExit):
        check_env.main([])
