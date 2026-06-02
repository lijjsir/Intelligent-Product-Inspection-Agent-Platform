def test_backend_app_imports():
    from main import app

    assert app.title == "PIAP Backend"


def test_health_live_endpoint_is_registered():
    from fastapi.testclient import TestClient
    from main import app

    response = TestClient(app).get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"
