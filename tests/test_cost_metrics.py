"""Unit tests for cost metric exporter (config/cost_exporter.py).

Verifies that cost coefficient gauges are correctly initialized from
config/settings.py at application startup.
"""

import pytest
from prometheus_client import REGISTRY

from config import settings
from config.cost_exporter import init_cost_metrics


def test_init_cost_metrics_sets_gauges_from_settings(monkeypatch):
    """Verify cost gauges are set to values from settings.py."""
    # Arrange: override settings with known test values
    monkeypatch.setattr(settings.settings, "cost_per_vcpu_hour_usd", 0.123)
    monkeypatch.setattr(settings.settings, "cost_per_gb_memory_hour_usd", 0.456)
    monkeypatch.setattr(settings.settings, "cost_per_gb_storage_month_usd", 0.789)

    # Act: initialize cost metrics
    init_cost_metrics()

    # Assert: verify gauges are set correctly
    vcpu_gauge = REGISTRY.get_sample_value("ledgerlens_cost_per_vcpu_hour_usd")
    memory_gauge = REGISTRY.get_sample_value("ledgerlens_cost_per_gb_memory_hour_usd")
    storage_gauge = REGISTRY.get_sample_value("ledgerlens_cost_per_gb_storage_month_usd")

    assert vcpu_gauge == pytest.approx(0.123), \
        f"Expected vCPU cost gauge = 0.123, got {vcpu_gauge}"
    assert memory_gauge == pytest.approx(0.456), \
        f"Expected memory cost gauge = 0.456, got {memory_gauge}"
    assert storage_gauge == pytest.approx(0.789), \
        f"Expected storage cost gauge = 0.789, got {storage_gauge}"


def test_init_cost_metrics_is_idempotent():
    """Verify calling init_cost_metrics() multiple times is safe (no-op after first call)."""
    # Arrange: call init once
    init_cost_metrics()
    first_call_value = REGISTRY.get_sample_value("ledgerlens_cost_per_vcpu_hour_usd")

    # Act: call init again
    init_cost_metrics()
    second_call_value = REGISTRY.get_sample_value("ledgerlens_cost_per_vcpu_hour_usd")

    # Assert: value unchanged (second call was a no-op)
    assert first_call_value == second_call_value, \
        "Repeated init_cost_metrics() calls should be no-ops"


def test_cost_gauges_are_exposed_at_metrics_endpoint(client):
    """Verify cost coefficient gauges appear in GET /metrics response."""
    # Arrange: initialize cost metrics
    init_cost_metrics()

    # Act: fetch /metrics
    response = client.get("/metrics")

    # Assert: cost gauges are present in the Prometheus text format output
    assert response.status_code == 200
    text = response.text

    assert "ledgerlens_cost_per_vcpu_hour_usd" in text, \
        "vCPU cost gauge missing from /metrics"
    assert "ledgerlens_cost_per_gb_memory_hour_usd" in text, \
        "Memory cost gauge missing from /metrics"
    assert "ledgerlens_cost_per_gb_storage_month_usd" in text, \
        "Storage cost gauge missing from /metrics"


def test_cost_gauges_with_default_values():
    """Verify default cost values from .env.example are reasonable (non-negative, non-zero)."""
    # Arrange: use actual settings (loaded from .env or defaults)
    # Act: initialize with default settings
    init_cost_metrics()

    # Assert: gauges are set to reasonable defaults
    vcpu_cost = REGISTRY.get_sample_value("ledgerlens_cost_per_vcpu_hour_usd")
    memory_cost = REGISTRY.get_sample_value("ledgerlens_cost_per_gb_memory_hour_usd")
    storage_cost = REGISTRY.get_sample_value("ledgerlens_cost_per_gb_storage_month_usd")

    assert vcpu_cost is not None, "vCPU cost gauge not initialized"
    assert vcpu_cost >= 0, f"vCPU cost must be non-negative, got {vcpu_cost}"
    assert vcpu_cost < 1.0, f"vCPU cost suspiciously high: {vcpu_cost} (sanity check failed)"

    assert memory_cost is not None, "Memory cost gauge not initialized"
    assert memory_cost >= 0, f"Memory cost must be non-negative, got {memory_cost}"
    assert memory_cost < 1.0, f"Memory cost suspiciously high: {memory_cost} (sanity check failed)"

    assert storage_cost is not None, "Storage cost gauge not initialized"
    assert storage_cost >= 0, f"Storage cost must be non-negative, got {storage_cost}"
    assert storage_cost < 1.0, f"Storage cost suspiciously high: {storage_cost} (sanity check failed)"


# Note: settings-validation tests (negative cost, capacity projection validation)
# have been moved to tests/test_settings.py to keep test scope aligned.
