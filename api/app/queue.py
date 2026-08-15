import os
import time
import uuid

import redis
from redis.exceptions import ResponseError


STREAM_NAME = "check_jobs"
GROUP_NAME = "check_workers"
LOCK_TTL_SECONDS = 3600
COMPONENT_HEARTBEAT_TTL_SECONDS = 120

client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "redis"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    decode_responses=True,
)


def ensure_consumer_group():
    try:
        client.xgroup_create(
            STREAM_NAME,
            GROUP_NAME,
            id="0",
            mkstream=True,
        )
    except ResponseError as error:
        if "BUSYGROUP" not in str(error):
            raise


def write_component_heartbeat(component_name: str):
    client.set(
        f"system:{component_name}:last_seen",
        str(time.time()),
        ex=COMPONENT_HEARTBEAT_TTL_SECONDS,
    )


def get_queue_health():
    started_at = time.perf_counter()
    client.ping()
    redis_latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

    try:
        pending = client.xpending(STREAM_NAME, GROUP_NAME)["pending"]
    except ResponseError:
        pending = 0

    return {
        "redis_latency_ms": redis_latency_ms,
        "stream_jobs": client.xlen(STREAM_NAME),
        "pending_jobs": pending,
        "scheduler_last_seen": client.get("system:scheduler:last_seen"),
        "worker_last_seen": client.get("system:worker:last_seen"),
    }


def lock_key(monitor_id: int):
    return f"monitor:{monitor_id}:queued"


def enqueue_check(monitor_id: int):
    key = lock_key(monitor_id)
    acquired = client.set(key, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        return False

    try:
        client.xadd(
            STREAM_NAME,
            {
                "monitor_id": monitor_id,
                "job_id": str(uuid.uuid4()),
            },
        )
    except Exception:
        client.delete(key)
        raise
    return True


def read_check(consumer_name: str):
    pending = client.xreadgroup(
        GROUP_NAME,
        consumer_name,
        {STREAM_NAME: "0"},
        count=1,
    )
    if pending and pending[0][1]:
        return pending[0][1][0]

    fresh = client.xreadgroup(
        GROUP_NAME,
        consumer_name,
        {STREAM_NAME: ">"},
        count=1,
        block=5000,
    )
    if fresh and fresh[0][1]:
        return fresh[0][1][0]
    return None


def acknowledge_check(message_id: str, monitor_id: int):
    pipeline = client.pipeline()
    pipeline.xack(STREAM_NAME, GROUP_NAME, message_id)
    pipeline.xdel(STREAM_NAME, message_id)
    pipeline.delete(lock_key(monitor_id))
    pipeline.execute()
