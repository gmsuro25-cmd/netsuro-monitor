from __future__ import annotations

import os


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class InvalidRequestOrigin(ValueError):
    pass


def allowed_origins() -> set[str]:
    return {
        origin.strip().rstrip("/")
        for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    }


def validate_request_origin(method: str, path: str, origin: str | None):
    if method not in UNSAFE_METHODS or path.startswith("/heartbeats/"):
        return

    if origin:
        if origin.rstrip("/") not in allowed_origins():
            raise InvalidRequestOrigin("request origin is not allowed")
        return

    if os.environ.get("REQUIRE_ORIGIN", "false").lower() == "true":
        raise InvalidRequestOrigin("request origin is required")


def allowed_hosts() -> list[str]:
    configured = os.environ.get(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1,api",
    )
    return [host.strip() for host in configured.split(",") if host.strip()]
