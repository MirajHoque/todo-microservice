"""Tests for GET /health and the request-ID middleware.

TestClient calls the app in-process — no server, no network — so
tests are fast and need nothing running. Run: make test
"""

from fastapi.testclient import TestClient

from agent.main import app

client = TestClient(app)


def test_health_ok():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "agent"


def test_request_id_is_generated():
    res = client.get("/health")
    assert res.headers["X-Request-ID"]  # a new UUID when the caller sent none


def test_request_id_is_reused():
    # A caller (web, a load balancer) already chose an ID: keep it, so
    # the same ID shows up in every service's logs for this request.
    res = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert res.headers["X-Request-ID"] == "abc-123"
