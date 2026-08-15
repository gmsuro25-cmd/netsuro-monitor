from datetime import datetime, timedelta, timezone

from app.notifier import build_slack_message


def test_monitor_opened_message_contains_context():
    message = build_slack_message(
        {
            "source_type": "MONITOR_INCIDENT",
            "event_type": "OPENED",
            "project_name": "Production",
            "monitor_name": "Public API",
            "monitor_type": "HTTP",
            "monitor_url": "https://example.com/health",
            "cause": "Expected HTTP status 200, received 503",
            "started_at": datetime.now(timezone.utc),
            "resolved_at": None,
        }
    )["text"]

    assert "Production" in message
    assert "Public API" in message
    assert "received 503" in message


def test_monitor_resolved_message_contains_duration():
    started = datetime.now(timezone.utc) - timedelta(minutes=4)
    message = build_slack_message(
        {
            "source_type": "MONITOR_INCIDENT",
            "event_type": "RESOLVED",
            "project_name": "Production",
            "monitor_name": "Public API",
            "monitor_type": "HTTP",
            "monitor_url": "https://example.com/health",
            "cause": "timeout",
            "started_at": started,
            "resolved_at": started + timedelta(minutes=4),
        }
    )["text"]

    assert "resolved" in message
    assert "4 minutes" in message
