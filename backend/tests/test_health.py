from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


def test_health_check() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "success": True,
        "data": {"status": "ok"},
        "error": None,
        "meta": None,
        "request_id": body["request_id"],
    }
    UUID(body["request_id"])
    assert response.headers["X-Request-ID"] == body["request_id"]
