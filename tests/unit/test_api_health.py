from fastapi.testclient import TestClient

from medparse.api import app


def test_health_endpoint_reports_ready_state() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload == {"status": "ok", "ready": True}

        probe = client.get("/healthz")
        assert probe.status_code == 200
        assert probe.json() == {"ok": True, "ready": True, "status": "ok"}
