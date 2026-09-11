"""Regression coverage for the api/api_key_router.py cleanup (Issue #409)."""

from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from config.settings import settings as _settings


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "api_keys.db")
    with patch.object(_settings, "ledgerlens_db_path", path):
        yield path


@pytest.fixture
def app(db_path):
    from api.api_key_router import router, require_scope
    from api.auth import require_admin_key

    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[require_admin_key] = lambda: None

    @test_app.get("/scores", dependencies=[Depends(require_scope("read:scores"))])
    def _scores() -> dict:
        return {"ok": True}

    return test_app


def test_rotate_rejects_non_positive_grace_period(app):
    """The 422 guard runs before the store call, so it is not swallowed as a 400."""
    client = TestClient(app)
    resp = client.post("/admin/api-keys/some-key/rotate", params={"grace_period_seconds": 0})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Grace period must be positive"


def test_rotate_unknown_key_returns_400(app):
    client = TestClient(app)
    resp = client.post("/admin/api-keys/does-not-exist/rotate")
    assert resp.status_code == 400


def test_create_rejects_invalid_scope(app):
    client = TestClient(app)
    resp = client.post("/admin/api-keys", json={"scopes": ["not:a:scope"]})
    assert resp.status_code == 422


def test_require_scope_enforces_scopes(app, db_path):
    from detection.api_key_store import create_api_key

    client = TestClient(app)

    assert client.get("/scores").status_code == 401
    assert client.get("/scores", headers={"X-LedgerLens-Api-Key": "bogus"}).status_code == 401

    wrong = create_api_key(scopes=["write:suppressions"])
    resp = client.get("/scores", headers={"X-LedgerLens-Api-Key": wrong["plaintext_key"]})
    assert resp.status_code == 403

    right = create_api_key(scopes=["read:scores"])
    resp = client.get("/scores", headers={"X-LedgerLens-Api-Key": right["plaintext_key"]})
    assert resp.status_code == 200

    # An `admin` key satisfies any required scope.
    admin = create_api_key(scopes=["admin"])
    resp = client.get("/scores", headers={"X-LedgerLens-Api-Key": admin["plaintext_key"]})
    assert resp.status_code == 200


def test_revoke_unknown_key_returns_404(app):
    client = TestClient(app)
    assert client.delete("/admin/api-keys/does-not-exist").status_code == 404
