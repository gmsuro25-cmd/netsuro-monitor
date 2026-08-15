import pytest
from pydantic import ValidationError

from app.schemas import MonitorCreate


def test_http_monitor_requires_url():
    with pytest.raises(ValidationError):
        MonitorCreate(project_id=1, monitor_type="HTTP", name="API")


def test_heartbeat_does_not_require_url():
    monitor = MonitorCreate(
        project_id=1,
        monitor_type="HEARTBEAT",
        name="Daily job",
        interval_seconds=60,
    )
    assert monitor.url is None


def test_monitor_rejects_interval_below_thirty_seconds():
    with pytest.raises(ValidationError):
        MonitorCreate(
            project_id=1,
            monitor_type="HTTP",
            name="API",
            url="https://example.com",
            interval_seconds=29,
        )
