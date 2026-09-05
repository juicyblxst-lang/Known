from fastapi.testclient import TestClient

from app.auth import AuthContext, require_auth
from app.main import app
from app.api import store


def test_customers_endpoint_requires_authentication():
    client = TestClient(app)
    response = client.get("/api/customers")
    assert response.status_code == 401


def test_workspace_endpoint_requires_authentication():
    client = TestClient(app)
    response = client.get("/api/workspace/customer-1")
    assert response.status_code == 401


def test_session_endpoint_requires_authentication():
    client = TestClient(app)
    response = client.get("/api/sessions/session-1?customer_id=customer-1")
    assert response.status_code == 401


def test_authenticated_customer_endpoint_uses_auth_context(monkeypatch):
    async def fake_auth() -> AuthContext:
        return AuthContext(user_id="user-1", business_id="business-1")

    monkeypatch.setattr(store, "customers", lambda business_id: [])
    app.dependency_overrides[require_auth] = fake_auth
    try:
        client = TestClient(app)
        response = client.get("/api/customers")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
