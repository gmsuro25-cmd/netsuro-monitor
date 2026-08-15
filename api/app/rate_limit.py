import hashlib
import os

import redis
from fastapi import Request


INCREMENT_WINDOW = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, retry_after)


class RateLimiterUnavailable(Exception):
    pass


class RateLimiter:
    def __init__(self, client=None):
        self.client = client or redis.Redis(
            host=os.environ.get("REDIS_HOST", "redis"),
            port=int(os.environ.get("REDIS_PORT", "6379")),
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )

    def check(self, scope: str, identity: str, limit: int, window_seconds: int):
        digest = hashlib.sha256(identity.encode()).hexdigest()
        key = f"rate:{scope}:{digest}"
        try:
            count, ttl = self.client.eval(INCREMENT_WINDOW, 1, key, window_seconds)
        except redis.RedisError as error:
            raise RateLimiterUnavailable() from error
        if int(count) > limit:
            raise RateLimitExceeded(int(ttl))


limiter = RateLimiter()


def _setting(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _client_ip(request: Request) -> str:
    if os.environ.get("TRUST_PROXY_HEADERS", "false").lower() == "true":
        forwarded = request.headers.get("x-real-ip")
        if forwarded:
            return forwarded.strip()
    return request.client.host if request.client else "unknown"


def apply_rate_limits(request: Request) -> bool:
    """Apply endpoint-specific limits and return whether failure must be closed."""
    path = request.url.path
    method = request.method
    client_ip = _client_ip(request)

    if method == "POST" and path == "/auth/login":
        limiter.check("login-minute", client_ip, _setting("RATE_LIMIT_LOGIN_PER_MINUTE", 5), 60)
        limiter.check("login-hour", client_ip, _setting("RATE_LIMIT_LOGIN_PER_HOUR", 20), 3600)
        return True

    if method == "POST" and path.startswith("/heartbeats/"):
        token = path.removeprefix("/heartbeats/")
        limiter.check("heartbeat-token", token, _setting("RATE_LIMIT_HEARTBEAT_PER_MINUTE", 30), 60)
        limiter.check("heartbeat-ip", client_ip, _setting("RATE_LIMIT_HEARTBEAT_IP_PER_MINUTE", 300), 60)
        return True

    if path == "/health/live":
        limiter.check("liveness-ip", client_ip, _setting("RATE_LIMIT_LIVENESS_PER_MINUTE", 120), 60)
        return False

    session_token = request.cookies.get("netsuro_session")
    identity = session_token or client_ip
    if method == "POST" and path.startswith("/monitors/") and path.endswith("/check"):
        limiter.check("manual-check", identity, _setting("RATE_LIMIT_MANUAL_CHECK_PER_MINUTE", 5), 60)
        return False

    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        limiter.check("api-write", identity, _setting("RATE_LIMIT_WRITE_PER_MINUTE", 60), 60)
    else:
        limiter.check("api-read", identity, _setting("RATE_LIMIT_READ_PER_MINUTE", 300), 60)
    return False
