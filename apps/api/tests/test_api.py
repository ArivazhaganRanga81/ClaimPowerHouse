from __future__ import annotations

from app.database import get_session
from app.main import app
from app.security import Principal, get_principal
from fastapi.testclient import TestClient


def test_claim_queue_and_detail(session_factory):
    def override_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="test-user", role="ADJUDICATOR", display_name="Test User"
    )
    try:
        with TestClient(app) as client:
            queue = client.get("/api/v1/claims")
            assert queue.status_code == 200
            payload = queue.json()
            assert payload["total"] == 20
            claim_id = payload["items"][0]["id"]
            detail = client.get(f"/api/v1/claims/{claim_id}")
            assert detail.status_code == 200
            assert detail.json()["lines"]
    finally:
        app.dependency_overrides.clear()
