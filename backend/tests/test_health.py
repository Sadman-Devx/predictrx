from rest_framework.test import APIClient


def test_health_ok():
    r = APIClient().get("/api/health/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
