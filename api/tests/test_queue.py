from app import queue


class FakeRedis:
    def __init__(self, lock_acquired=True, xadd_error=None):
        self.lock_acquired = lock_acquired
        self.xadd_error = xadd_error
        self.added = []
        self.deleted = []

    def set(self, *args, **kwargs):
        return self.lock_acquired

    def xadd(self, stream, fields):
        if self.xadd_error:
            raise self.xadd_error
        self.added.append((stream, fields))

    def delete(self, key):
        self.deleted.append(key)


def test_enqueue_uses_lock_to_prevent_duplicate_jobs(monkeypatch):
    fake = FakeRedis(lock_acquired=False)
    monkeypatch.setattr(queue, "client", fake)

    assert queue.enqueue_check(42) is False
    assert fake.added == []


def test_enqueue_releases_lock_when_stream_write_fails(monkeypatch):
    fake = FakeRedis(xadd_error=RuntimeError("Redis failed"))
    monkeypatch.setattr(queue, "client", fake)

    try:
        queue.enqueue_check(42)
    except RuntimeError:
        pass

    assert fake.deleted == [queue.lock_key(42)]
