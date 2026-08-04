from fastapi.testclient import TestClient

from titan.app.main import app


def test_health_reports_ok_with_working_database():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
