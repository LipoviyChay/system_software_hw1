import string

from fastapi.testclient import TestClient

from sysapp.main import app, make_password

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_password_default():
    r = client.get("/api/password")
    assert r.status_code == 200
    d = r.json()
    assert len(d["password"]) == 16
    assert d["strength"] in {"слабый", "средний", "хороший", "отличный"}
    assert d["entropy_bits"] > 80


def test_password_options_respected():
    d = client.get("/api/password", params={"length": 20, "upper": False,
                                            "digits": False, "symbols": False}).json()
    assert len(d["password"]) == 20
    assert all(c in string.ascii_lowercase for c in d["password"])


def test_password_contains_each_selected_group():
    for _ in range(50):
        pw, _ = make_password(8, True, True, True)
        assert any(c in string.ascii_lowercase for c in pw)
        assert any(c in string.ascii_uppercase for c in pw)
        assert any(c in string.digits for c in pw)
        assert any(c not in string.ascii_letters + string.digits for c in pw)


def test_password_length_validation():
    assert client.get("/api/password", params={"length": 3}).status_code == 422
    assert client.get("/api/password", params={"length": 500}).status_code == 422


def test_counters_and_monitoring():
    before = client.get("/api/stats").json()
    client.get("/")
    client.get("/api/password")
    after = client.get("/api/stats").json()
    assert after["visits"] == before["visits"] + 1
    assert after["passwords_generated"] == before["passwords_generated"] + 1

    d = client.get("/api/monitoring").json()
    assert d["health"] == "OK"
    assert d["passwords"]["last_hour"] >= 1
    assert len(d["visits"]["by_hour_last_24h"]) == 24
    assert d["resources"]["process_memory_mb"] > 0
    assert "Мониторинг" in client.get("/monitoring").text
    body = client.get("/metrics").text
    assert "app_passwords_generated_total" in body
