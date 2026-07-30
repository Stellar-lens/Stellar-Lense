"""Pytest configuration and shared fixtures."""

import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set environment variables for tests
os.environ.setdefault("MODEL_DIR", "./models")
os.environ.setdefault("RISK_SCORE_DB_URL", "sqlite:///:memory:")
os.environ.setdefault("WATCHED_ASSET_PAIRS", "USDC:native,BTC:native,XLM:native")
os.environ.setdefault("BENFORD_WINDOWS_HOURS", "1,4,24,168,720")
os.environ.setdefault("MIN_TRADES_FOR_SCORING", "20")

# Hypothesis configuration for property-based tests (issue #205)
from hypothesis import HealthCheck, settings

# Configure Hypothesis for CI environment
settings.register_profile(
    "ci",
    max_examples=500,           # Reasonable number for CI
    deadline=5000,              # 5 seconds per example
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

settings.register_profile(
    "dev",
    max_examples=50,            # Faster for local development
    deadline=2000,
)

# Select profile based on environment
import os

if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    settings.load_profile("ci")
else:
    settings.load_profile("dev")

# Typed deployment-mode fixtures (Issue #543) — reusable, validated Config
# overlays for local/testnet/production. Each fixture restores prior Config
# state on teardown, so tests using it never leak overrides into other tests.
import pytest

from config.deployment_modes import DeploymentMode, apply_deployment_mode


@pytest.fixture
def local_deployment_config():
    with apply_deployment_mode(DeploymentMode.LOCAL) as fixture:
        yield fixture


@pytest.fixture
def testnet_deployment_config():
    with apply_deployment_mode(DeploymentMode.TESTNET) as fixture:
        yield fixture


@pytest.fixture
def production_deployment_config():
    with apply_deployment_mode(DeploymentMode.PRODUCTION) as fixture:
        yield fixture


# Source package integrity check (Issue #540) — runs once before any test
# collects. A structurally broken tree (missing __init__.py, unresolved
# merge conflict markers, syntax errors) fails the whole session immediately
# with a single readable report instead of surfacing as a scatter of
# unrelated collection/import errors across the suite.
def pytest_sessionstart(session):  # noqa: ARG001
    from utils.package_integrity import check_source_package_integrity

    report = check_source_package_integrity(root=project_root)
    if not report.ok:
        pytest.exit(f"\n{report.render()}", returncode=1)
