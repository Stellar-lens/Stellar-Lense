import pytest

import config.settings as settings_module


def test_defaults_when_env_unset(monkeypatch):
    for key in (
        "HORIZON_URL",
        "BENFORD_MAD_THRESHOLD",
        "RISK_SCORE_THRESHOLD",
        "MODEL_DIR",
        "LEDGERLENS_DB_PATH",
        "ENSEMBLE_WEIGHT_RF",
        "ENSEMBLE_WEIGHT_XGB",
        "ENSEMBLE_WEIGHT_LGBM",
        "STREAMER_QUEUE_MAXSIZE",
        "STREAMER_OVERFLOW_STRATEGY",
        "STREAMER_HIGH_WATER_RATIO",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = settings_module.Settings()

    assert settings.horizon_url == "https://horizon.stellar.org"
    assert settings.benford_mad_threshold == 0.015
    assert settings.risk_score_threshold == 70
    assert settings.model_dir == "./models"
    assert settings.db_path == "./ledgerlens.db"
    assert settings.ensemble_weight_rf == 0.25
    assert settings.ensemble_weight_xgb == 0.50
    assert settings.ensemble_weight_lgbm == 0.25
    assert settings.streamer_queue_maxsize == 1000
    assert settings.streamer_overflow_strategy == "drop_oldest"
    assert settings.streamer_high_water_ratio == 0.8


def test_env_overrides_are_applied(monkeypatch):
    monkeypatch.setenv("RISK_SCORE_THRESHOLD", "85")
    monkeypatch.setenv("LEDGERLENS_DB_PATH", "/tmp/custom.db")
    monkeypatch.setenv("ENSEMBLE_WEIGHT_RF", "2")
    monkeypatch.setenv("ENSEMBLE_WEIGHT_XGB", "3")
    monkeypatch.setenv("ENSEMBLE_WEIGHT_LGBM", "5")

    settings = settings_module.Settings()

    assert settings.risk_score_threshold == 85
    assert settings.db_path == "/tmp/custom.db"
    assert settings.ensemble_weight_rf == 2
    assert settings.ensemble_weight_xgb == 3
    assert settings.ensemble_weight_lgbm == 5


def test_negative_ensemble_weight_raises(monkeypatch):
    monkeypatch.setenv("ENSEMBLE_WEIGHT_RF", "-0.01")

    with pytest.raises(ValueError, match="Ensemble weights must be non-negative"):
        settings_module.Settings()


def test_all_zero_ensemble_weights_raise(monkeypatch):
    monkeypatch.setenv("ENSEMBLE_WEIGHT_RF", "0")
    monkeypatch.setenv("ENSEMBLE_WEIGHT_XGB", "0")
    monkeypatch.setenv("ENSEMBLE_WEIGHT_LGBM", "0")

    with pytest.raises(ValueError, match="At least one ensemble weight must be positive"):
        settings_module.Settings()


def test_cors_wildcard_origin_raises(monkeypatch):
    monkeypatch.setenv("LEDGERLENS_CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValueError, match="must not contain '\\*'"):
        settings_module.Settings()


def test_cors_wildcard_in_list_raises(monkeypatch):
    monkeypatch.setenv("LEDGERLENS_CORS_ALLOWED_ORIGINS", "https://ok.example.com,*")

    with pytest.raises(ValueError, match="must not contain '\\*'"):
        settings_module.Settings()


def test_cors_default_is_empty_tuple(monkeypatch):
    monkeypatch.delenv("LEDGERLENS_CORS_ALLOWED_ORIGINS", raising=False)

    settings = settings_module.Settings()

    assert settings.cors_allowed_origins == ()


# ── Cost & Capacity settings validation ─────────────────────────────────


def test_default_cost_coefficients_are_reasonable():
    """Verify default cost coefficient values are non-negative and within sane bounds."""
    settings = settings_module.Settings()
    assert settings.cost_per_vcpu_hour_usd >= 0
    assert settings.cost_per_vcpu_hour_usd < 1.0
    assert settings.cost_per_gb_memory_hour_usd >= 0
    assert settings.cost_per_gb_memory_hour_usd < 1.0
    assert settings.cost_per_gb_storage_month_usd >= 0
    assert settings.cost_per_gb_storage_month_usd < 10.0


def test_default_capacity_projection_days_are_reasonable():
    """Verify default capacity projection settings are >= 1."""
    settings = settings_module.Settings()
    assert settings.capacity_projection_window_days >= 1
    assert settings.capacity_projection_lead_time_days >= 1


def test_negative_cost_coefficient_rejected(monkeypatch):
    """Verify that pydantic rejects negative cost coefficients at Settings load time."""
    import os
    from pydantic import ValidationError

    original_value = os.environ.get("COST_PER_VCPU_HOUR_USD")
    os.environ["COST_PER_VCPU_HOUR_USD"] = "-0.01"

    try:
        with pytest.raises(ValidationError, match="Cost coefficients must be non-negative"):
            settings_module.Settings()
    finally:
        if original_value is not None:
            os.environ["COST_PER_VCPU_HOUR_USD"] = original_value
        else:
            os.environ.pop("COST_PER_VCPU_HOUR_USD", None)


def test_capacity_projection_window_validation(monkeypatch):
    """Verify capacity projection window must be >= 1 day."""
    import os
    from pydantic import ValidationError

    original_value = os.environ.get("CAPACITY_PROJECTION_WINDOW_DAYS")
    os.environ["CAPACITY_PROJECTION_WINDOW_DAYS"] = "0"

    try:
        with pytest.raises(ValidationError, match="Capacity projection days must be >= 1"):
            settings_module.Settings()
    finally:
        if original_value is not None:
            os.environ["CAPACITY_PROJECTION_WINDOW_DAYS"] = original_value
        else:
            os.environ.pop("CAPACITY_PROJECTION_WINDOW_DAYS", None)


def test_capacity_projection_lead_time_validation(monkeypatch):
    """Verify capacity projection lead time must be >= 1 day."""
    import os
    from pydantic import ValidationError

    original_value = os.environ.get("CAPACITY_PROJECTION_LEAD_TIME_DAYS")
    os.environ["CAPACITY_PROJECTION_LEAD_TIME_DAYS"] = "-5"

    try:
        with pytest.raises(ValidationError, match="Capacity projection days must be >= 1"):
            settings_module.Settings()
    finally:
        if original_value is not None:
            os.environ["CAPACITY_PROJECTION_LEAD_TIME_DAYS"] = original_value
        else:
            os.environ.pop("CAPACITY_PROJECTION_LEAD_TIME_DAYS", None)
