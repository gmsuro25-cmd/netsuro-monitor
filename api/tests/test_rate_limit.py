import pytest

from app.rate_limit import RateLimitExceeded, RateLimiter


class FakeRedis:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.keys = []

    def eval(self, script, key_count, key, window):
        self.keys.append(key)
        return next(self.responses)


def test_request_within_limit_is_allowed():
    client = FakeRedis([(5, 42)])
    RateLimiter(client).check("login-minute", "203.0.113.10", 5, 60)


def test_request_over_limit_returns_retry_time():
    client = FakeRedis([(6, 37)])
    with pytest.raises(RateLimitExceeded) as captured:
        RateLimiter(client).check("login-minute", "203.0.113.10", 5, 60)
    assert captured.value.retry_after == 37


def test_identity_is_hashed_before_storing_in_redis():
    secret = "heartbeat-secret-token"
    client = FakeRedis([(1, 60)])
    RateLimiter(client).check("heartbeat-token", secret, 30, 60)
    assert secret not in client.keys[0]
