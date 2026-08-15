import ipaddress
import os
import socket
from urllib.parse import urlsplit


class UnsafeMonitorTargetError(ValueError):
    pass


def _allowed_private_hosts() -> set[str]:
    return {
        host.strip().lower().rstrip(".")
        for host in os.environ.get("MONITOR_ALLOWED_PRIVATE_HOSTS", "").split(",")
        if host.strip()
    }


def _allowed_ports() -> set[int]:
    value = os.environ.get("MONITOR_ALLOWED_PORTS", "80,443")
    try:
        return {int(port.strip()) for port in value.split(",") if port.strip()}
    except ValueError as error:
        raise RuntimeError("MONITOR_ALLOWED_PORTS must contain comma-separated integers") from error


def validate_monitor_url(url: str) -> str:
    parsed = urlsplit(str(url))
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeMonitorTargetError("only HTTP and HTTPS monitor targets are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeMonitorTargetError("monitor target URLs cannot contain credentials")
    if not parsed.hostname:
        raise UnsafeMonitorTargetError("monitor target hostname is required")

    hostname = parsed.hostname.lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in _allowed_ports():
        raise UnsafeMonitorTargetError(f"monitor target port {port} is not allowed")

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as error:
        raise UnsafeMonitorTargetError("monitor target hostname could not be resolved") from error

    if not addresses:
        raise UnsafeMonitorTargetError("monitor target hostname resolved to no addresses")

    private_host_allowed = hostname in _allowed_private_hosts()
    for address in addresses:
        ip = ipaddress.ip_address(address)
        # Link-local includes cloud metadata ranges and is never configurable.
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise UnsafeMonitorTargetError(f"monitor target resolved to blocked address {ip}")
        if not ip.is_global and not private_host_allowed:
            raise UnsafeMonitorTargetError(f"monitor target resolved to non-public address {ip}")

    return str(url)
