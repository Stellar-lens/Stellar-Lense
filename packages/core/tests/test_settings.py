"""Tests for config/settings.py.

Every test builds its own ``Settings()`` instance from a cleaned environment,
so a stray ``.env`` or a previous test can't leak values in.
"""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

import config.settings as settings_module

_SETTINGS_ENV_VARS = (
    "HORIZON_URL",
    "NETWORK",
    "BENFORD_MAD_THRESHOLD",
    "RISK_SCORE_THRESHOLD",
    "MODEL_DIR",
    "DB_PATH",
    "TRADE_HISTORY_LOOKBACK_DAYS",
    "HORIZON_MAX_RETRIES",
)


@pytest.fixture(autouse=True)
def _clean_settings_env(monkeypatch):
    for key in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_when_env_unset():
    settings = settings_module.Settings(_env_file=None)
    assert settings.horizon_url == "https://horizon.stellar.org"
    assert settings.network == "testnet"
    assert settings.benford_mad_threshold == 0.015
    assert settings.risk_score_threshold == 70
    assert settings.model_dir == "./models"
    assert settings.db_path == "./stellar_lense.db"
    assert settings.trade_history_lookback_days == 30


def test_env_overrides_are_applied(monkeypatch):
    monkeypatch.setenv("RISK_SCORE_THRESHOLD", "85")
    monkeypatch.setenv("DB_PATH", "/tmp/custom.db")
    monkeypatch.setenv("HORIZON_URL", "https://horizon-testnet.stellar.org")
    settings = settings_module.Settings(_env_file=None)
    assert settings.risk_score_threshold == 85
    assert settings.db_path == "/tmp/custom.db"
    assert settings.horizon_url == "https://horizon-testnet.stellar.org"


@pytest.mark.parametrize("value", ["-1", "101"])
def test_risk_score_threshold_out_of_range_raises(monkeypatch, value):
    monkeypatch.setenv("RISK_SCORE_THRESHOLD", value)
    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "100"])
def test_risk_score_threshold_boundary_values_accepted(monkeypatch, value):
    monkeypatch.setenv("RISK_SCORE_THRESHOLD", value)
    assert settings_module.Settings(_env_file=None).risk_score_threshold == int(value)


def test_negative_benford_threshold_raises(monkeypatch):
    monkeypatch.setenv("BENFORD_MAD_THRESHOLD", "-0.1")
    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)


def test_non_positive_lookback_raises(monkeypatch):
    monkeypatch.setenv("TRADE_HISTORY_LOOKBACK_DAYS", "0")
    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)


def test_horizon_url_requires_http_scheme(monkeypatch):
    monkeypatch.setenv("HORIZON_URL", "ftp://horizon.example")
    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)


def test_network_mainnet_accepted(monkeypatch):
    monkeypatch.setenv("NETWORK", "MAINNET")
    assert settings_module.Settings(_env_file=None).network == "mainnet"


def test_network_invalid_value_raises(monkeypatch):
    monkeypatch.setenv("NETWORK", "futurenet-ish")
    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)


def test_no_duplicate_field_declarations():
    tree = ast.parse(Path(settings_module.__file__).read_text(encoding="utf-8"))
    settings_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    names = [
        node.target.id
        for node in settings_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    ]
    assert len(names) == len(set(names))
