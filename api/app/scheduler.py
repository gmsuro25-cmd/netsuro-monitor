import os
import time

import httpx

from app.database import (
    connect,
    create_check,
    list_due_heartbeat_monitors,
    list_due_monitors,
    record_system_health,
)
from app.queue import enqueue_check, ensure_consumer_group, get_queue_health, write_component_heartbeat


POLL_SECONDS = int(os.environ.get("SCHEDULER_POLL_SECONDS", "10"))
SYSTEM_SAMPLE_SECONDS = 60


def timed_http_component(component: str, url: str):
    started_at = time.perf_counter()
    try:
        response = httpx.get(url, timeout=3)
        response.raise_for_status()
        duration = round((time.perf_counter() - started_at) * 1000, 2)
        return {"component": component, "status": "UP", "response_time_ms": duration, "detail": f"Response in {duration} ms"}
    except Exception as error:
        return {"component": component, "status": "DOWN", "detail": str(error)}


def record_system_snapshot():
    samples = [
        timed_http_component("api", "http://api:8000/health/live"),
        timed_http_component("web", "http://web/health"),
    ]
    started_at = time.perf_counter()
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        duration = round((time.perf_counter() - started_at) * 1000, 2)
        samples.append({"component": "database", "status": "UP", "response_time_ms": duration, "detail": f"Response in {duration} ms"})
    except Exception as error:
        samples.append({"component": "database", "status": "DOWN", "detail": str(error)})

    try:
        queue = get_queue_health()
        worker_is_fresh = bool(
            queue["worker_last_seen"]
            and time.time() - float(queue["worker_last_seen"]) <= 30
        )
        samples.extend([
            {"component": "redis", "status": "UP", "response_time_ms": queue["redis_latency_ms"], "detail": f"Response in {queue['redis_latency_ms']} ms"},
            {"component": "scheduler", "status": "UP", "detail": "Scheduler active"},
            {"component": "worker", "status": "UP" if worker_is_fresh else "DOWN", "detail": "Recent worker signal" if worker_is_fresh else "No recent worker signal"},
            {"component": "queue", "status": "UP", "stream_jobs": queue["stream_jobs"], "pending_jobs": queue["pending_jobs"], "detail": f"{queue['stream_jobs']} queued · {queue['pending_jobs']} processing"},
        ])
    except Exception as error:
        samples.extend({"component": component, "status": "DOWN", "detail": str(error)} for component in ["redis", "scheduler", "worker", "queue"])
    record_system_health(samples)


def enqueue_due_checks():
    for monitor in list_due_monitors():
        if enqueue_check(monitor["id"]):
            print(f"monitor={monitor['id']} enqueued", flush=True)


def record_overdue_heartbeats():
    for monitor in list_due_heartbeat_monitors():
        bucket = int(time.time() // monitor["interval_seconds"])
        create_check(
            {
                "job_id": f"heartbeat-overdue:{monitor['id']}:{bucket}",
                "monitor_id": monitor["id"],
                "status_code": None,
                "response_time_ms": 0,
                "succeeded": False,
                "error_message": "heartbeat overdue",
            }
        )
        print(f"monitor={monitor['id']} heartbeat overdue", flush=True)


def main():
    ensure_consumer_group()
    print(f"scheduler started poll_seconds={POLL_SECONDS}", flush=True)
    next_system_sample_at = 0
    while True:
        try:
            write_component_heartbeat("scheduler")
        except Exception as error:
            print(f"scheduler heartbeat failed: {error}", flush=True)
        try:
            enqueue_due_checks()
            record_overdue_heartbeats()
        except Exception as error:
            print(f"scheduler monitor cycle failed: {error}", flush=True)
        if time.monotonic() >= next_system_sample_at:
            try:
                record_system_snapshot()
            except Exception as error:
                print(f"scheduler system snapshot failed: {error}", flush=True)
            finally:
                next_system_sample_at = time.monotonic() + SYSTEM_SAMPLE_SECONDS
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
