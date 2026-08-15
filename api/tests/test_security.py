import pytest

from app.security import InvalidRequestOrigin, validate_request_origin


def test_allowed_origin_can_modify_data(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://monitor.netsuro.com")
    monkeypatch.setenv("REQUIRE_ORIGIN", "true")
    validate_request_origin(
        "PATCH",
        "/monitors/1",
        "https://monitor.netsuro.com",
    )


def test_unknown_origin_is_rejected(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://monitor.netsuro.com")
    with pytest.raises(InvalidRequestOrigin):
        validate_request_origin("DELETE", "/monitors/1", "https://evil.example")


def test_missing_origin_is_rejected_in_production_mode(monkeypatch):
    monkeypatch.setenv("REQUIRE_ORIGIN", "true")
    with pytest.raises(InvalidRequestOrigin):
        validate_request_origin("POST", "/projects", None)


def test_heartbeat_does_not_require_browser_origin(monkeypatch):
    monkeypatch.setenv("REQUIRE_ORIGIN", "true")
    validate_request_origin("POST", "/heartbeats/secret-token", None)


def test_safe_read_does_not_require_origin(monkeypatch):
    monkeypatch.setenv("REQUIRE_ORIGIN", "true")
    validate_request_origin("GET", "/dashboard", None)
