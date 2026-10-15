from fastapi.testclient import TestClient

from sysapp.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_visit_counter_and_metrics():
    before = client.get("/api/stats").json()["visits"]
    assert client.get("/").status_code == 200
    after = client.get("/api/stats").json()["visits"]
    assert after == before + 1
    body = client.get("/metrics").text
    assert "app_visits_total" in body
    assert "app_up 1.0" in body


def test_monitoring_api_and_page():
    client.get("/")
    d = client.get("/api/monitoring").json()
    assert d["health"] == "OK"
    assert d["visits"]["last_hour"] >= 1
    assert len(d["visits"]["by_hour_last_24h"]) == 24
    assert d["resources"]["process_memory_mb"] > 0
    assert "Мониторинг" in client.get("/monitoring").text
