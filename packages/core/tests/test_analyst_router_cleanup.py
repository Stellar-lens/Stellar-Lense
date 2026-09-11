"""Regression coverage for the api/analyst.py cleanup (Issue #408).

Imports the router directly rather than through ``api.main`` so the suite does
not depend on unrelated modules being importable.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.settings import settings as _settings

VALID_WALLET = "G" + "A" * 55
INVALID_WALLET = "not-a-wallet"


@pytest.fixture
def client(tmp_path):
    path = str(tmp_path / "analyst.db")
    with patch.object(_settings, "ledgerlens_db_path", path):
        from api.analyst import router
        from api.auth import require_admin_key

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_admin_key] = lambda: None
        yield TestClient(app)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", f"/analyst/wallet/{INVALID_WALLET}", None),
        ("post", f"/analyst/wallet/{INVALID_WALLET}/claim", {"analyst_key_hash": "h"}),
        ("post", f"/analyst/wallet/{INVALID_WALLET}/release", {"analyst_key_hash": "h"}),
        ("post", f"/analyst/wallet/{INVALID_WALLET}/feedback", {"verdict": "needs_review"}),
    ],
)
def test_invalid_wallet_is_rejected(client, method, path, body):
    resp = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid Stellar wallet address format."


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", f"/analyst/wallet/{VALID_WALLET}", None),
        ("post", f"/analyst/wallet/{VALID_WALLET}/claim", {"analyst_key_hash": "h"}),
        ("post", f"/analyst/wallet/{VALID_WALLET}/release", {"analyst_key_hash": "h"}),
    ],
)
def test_unscored_wallet_returns_404(client, method, path, body):
    """The shared `_default_asset_pair` helper 404s consistently across endpoints."""
    resp = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert resp.status_code == 404
    assert VALID_WALLET in resp.json()["detail"]


def test_feedback_requires_an_active_claim(client):
    """Against a fresh database an unclaimed wallet yields 403, not a server error."""
    resp = client.post(
        f"/analyst/wallet/{VALID_WALLET}/feedback",
        json={"verdict": "needs_review", "analyst_key_hash": "h"},
    )
    assert resp.status_code == 403
    assert "Claim it first" in resp.json()["detail"]


def test_feedback_rejects_bad_review_started_at(client):
    resp = client.post(
        f"/analyst/wallet/{VALID_WALLET}/feedback",
        json={"verdict": "needs_review", "review_started_at": "yesterday"},
    )
    assert resp.status_code == 422
    assert "Invalid review_started_at" in resp.json()["detail"]


def test_feedback_export_rejects_bad_since(client):
    resp = client.get("/analyst/feedback", params={"since": "not-a-timestamp"})
    assert resp.status_code == 422
    assert "Invalid since timestamp" in resp.json()["detail"]


def test_wallet_pattern_uses_a_real_re_import():
    """The `__import__("re")` workaround was replaced by a module-level import."""
    import api.analyst as analyst

    assert analyst.re.__name__ == "re"
    assert analyst._WALLET_PATTERN.match(VALID_WALLET)
    assert not analyst._WALLET_PATTERN.match(INVALID_WALLET)
