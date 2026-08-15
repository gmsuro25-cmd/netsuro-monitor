import socket

import httpx
import pytest

from app.checker import check_url
from app.ssrf import UnsafeMonitorTargetError, validate_monitor_url


def resolve_to(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))],
    )


def test_public_https_target_is_allowed(monkeypatch):
    resolve_to(monkeypatch, "93.184.216.34")
    assert validate_monitor_url("https://example.com/health") == "https://example.com/health"


@pytest.mark.parametrize(
    "url,address",
    [
        ("http://localhost", "127.0.0.1"),
        ("http://database.internal", "10.0.0.10"),
        ("http://router.internal", "192.168.1.1"),
        ("http://169.254.169.254", "169.254.169.254"),
    ],
)
def test_internal_targets_are_blocked(monkeypatch, url, address):
    resolve_to(monkeypatch, address)
    with pytest.raises(UnsafeMonitorTargetError):
        validate_monitor_url(url)


def test_credentials_in_target_are_blocked(monkeypatch):
    resolve_to(monkeypatch, "93.184.216.34")
    with pytest.raises(UnsafeMonitorTargetError):
        validate_monitor_url("https://user:password@example.com")


def test_unapproved_port_is_blocked(monkeypatch):
    resolve_to(monkeypatch, "93.184.216.34")
    with pytest.raises(UnsafeMonitorTargetError):
        validate_monitor_url("https://example.com:8443/health")


def test_private_redirect_is_blocked_before_second_request(monkeypatch):
    def resolver(host, *args, **kwargs):
        address = "93.184.216.34" if host == "example.com" else "10.0.0.10"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://private.internal/secret"})

    result = check_url(
        "https://example.com/health",
        timeout_seconds=10,
        expected_status_code=200,
        transport=httpx.MockTransport(handler),
    )

    assert result["succeeded"] is False
    assert result["status_code"] is None
    assert "non-public address" in result["error_message"]
    assert calls == ["https://example.com/health"]
