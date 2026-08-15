import os
import time

from app.checker import check_url
from app.database import create_check, get_monitor
from app.queue import (
    acknowledge_check,
    ensure_consumer_group,
    read_check,
    write_component_heartbeat,
)


CONSUMER_NAME = os.environ.get("WORKER_CONSUMER_NAME", "worker-1")


def process_message(message_id: str, fields: dict):
    monitor_id = int(fields["monitor_id"])
    job_id = fields.get("job_id") or f"legacy:{message_id}"
    monitor = get_monitor(monitor_id)

    if monitor is None or not monitor["is_active"] or monitor["project_is_archived"]:
        acknowledge_check(message_id, monitor_id)
        print(f"monitor={monitor_id} skipped", flush=True)
        return

    result = check_url(
        url=monitor["url"],
        timeout_seconds=monitor["timeout_seconds"],
        expected_status_code=monitor["expected_status_code"],
    )
    result["monitor_id"] = monitor_id
    result["job_id"] = job_id
    saved_check = create_check(result)
    acknowledge_check(message_id, monitor_id)

    print(
        f"monitor={monitor_id} "
        f"status={saved_check['status_code']} "
        f"succeeded={saved_check['succeeded']} "
        f"duration_ms={saved_check['response_time_ms']}",
        flush=True,
    )


def main():
    ensure_consumer_group()
    print(f"worker started consumer={CONSUMER_NAME}", flush=True)

    while True:
        write_component_heartbeat("worker")
        message = read_check(CONSUMER_NAME)
        if message is None:
            continue

        message_id, fields = message
        try:
            process_message(message_id, fields)
        except Exception as error:
            print(f"worker job failed: {error}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
