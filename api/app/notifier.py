import os
import time

import httpx

from app.config import read_secret, require_production_value
from app.database import (
    claim_notification,
    mark_notification_failed,
    mark_notification_sent,
)


SLACK_WEBHOOK_URL = read_secret("SLACK_WEBHOOK_URL")
POLL_SECONDS = int(os.environ.get("NOTIFIER_POLL_SECONDS", "5"))


def format_duration(started_at, resolved_at):
    if resolved_at is None:
        return None
    seconds = max(0, int((resolved_at - started_at).total_seconds()))
    if seconds < 60:
        return f"{seconds} seconds"
    if seconds < 3600:
        return f"{seconds // 60} minutes"
    return f"{seconds // 3600} h {(seconds % 3600) // 60} min"


def build_slack_message(notification: dict):
    if notification["source_type"] == "MONITOR_INCIDENT":
        target = (
            notification["monitor_url"]
            if notification["monitor_type"] == "HTTP"
            else "Heartbeat signal"
        )
        if notification["event_type"] == "OPENED":
            return {
                "text": (
                    f"🔴 *Monitor incident opened*\n"
                    f"*Project:* {notification['project_name']}\n"
                    f"*Monitor:* {notification['monitor_name']}\n"
                    f"*Type:* {notification['monitor_type']}\n"
                    f"*Target:* {target}\n"
                    f"*Cause:* {notification['cause']}\n"
                    f"*Started:* {notification['started_at'].isoformat()}"
                )
            }
        duration = format_duration(
            notification["started_at"], notification["resolved_at"]
        )
        return {
            "text": (
                f"🟢 *Monitor incident resolved*\n"
                f"*Project:* {notification['project_name']}\n"
                f"*Monitor:* {notification['monitor_name']}\n"
                f"*Type:* {notification['monitor_type']}\n"
                f"*Target:* {target}\n"
                f"*Duration:* {duration}"
            )
        }

    component = notification["component"].upper()
    if notification["event_type"] == "OPENED":
        return {
            "text": (
                f"🔴 *Internal incident opened*\n"
                f"*Component:* {component}\n"
                f"*Status:* DOWN\n"
                f"*Cause:* {notification['cause']}\n"
                f"*Started:* {notification['started_at'].isoformat()}"
            )
        }
    duration = format_duration(notification["started_at"], notification["resolved_at"])
    return {
        "text": (
            f"🟢 *Internal incident resolved*\n"
            f"*Component:* {component}\n"
            f"*Status:* UP\n"
            f"*Duration:* {duration}"
        )
    }


def main():
    require_production_value("SLACK_WEBHOOK_URL", SLACK_WEBHOOK_URL, min_length=30)
    if not SLACK_WEBHOOK_URL:
        raise RuntimeError("SLACK_WEBHOOK_URL is required")
    print(f"notifier started poll_seconds={POLL_SECONDS}", flush=True)
    while True:
        notification = None
        try:
            notification = claim_notification()
            if notification is None:
                time.sleep(POLL_SECONDS)
                continue
            response = httpx.post(
                SLACK_WEBHOOK_URL,
                json=build_slack_message(notification),
                timeout=10,
            )
            response.raise_for_status()
            mark_notification_sent(notification["id"])
            print(f"notification={notification['id']} sent", flush=True)
        except Exception as error:
            if notification is not None:
                mark_notification_failed(
                    notification["id"], notification["attempts"], str(error)
                )
                print(
                    f"notification={notification['id']} failed: {error}",
                    flush=True,
                )
            else:
                print(f"notifier cycle failed: {error}", flush=True)
                time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
