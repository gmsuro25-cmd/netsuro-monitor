import hashlib
import secrets
import time
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth import ensure_initial_admin, login, logout, session_user
from app.backups import get_backup_summary

from app.checker import check_url
from app.database import (
    connect,
    create_check,
    create_monitor,
    create_project,
    delete_monitor,
    get_monitor,
    get_monitor_history,
    get_notification_summary,
    get_system_health_history,
    get_system_incident,
    list_checks,
    list_dashboard_monitors,
    list_incidents,
    list_monitors,
    list_notification_attempts,
    list_projects,
    list_system_incidents,
    record_heartbeat,
    retry_failed_notification,
    rotate_heartbeat_token,
    update_monitor,
    update_project,
)
from app.schemas import (
    CheckResponse,
    DashboardMonitorResponse,
    IncidentResponse,
    LoginRequest,
    HeartbeatTokenResponse,
    MonitorCreate,
    MonitorCreatedResponse,
    MonitorHistoryResponse,
    MonitorResponse,
    MonitorUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.queue import get_queue_health
from app.rate_limit import (
    RateLimitExceeded,
    RateLimiterUnavailable,
    apply_rate_limits,
)
from app.security import (
    InvalidRequestOrigin,
    allowed_hosts,
    validate_request_origin,
)


@asynccontextmanager
async def lifespan(app):
    ensure_initial_admin()
    yield


app = FastAPI(title="Netsuro Monitor API", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
COOKIE_NAME = "netsuro_session"
PUBLIC_PATHS = {"/health/live", "/auth/login"}


@app.middleware("http")
async def require_session(request: Request, call_next):
    path = request.url.path
    try:
        validate_request_origin(
            request.method,
            path,
            request.headers.get("origin"),
        )
    except InvalidRequestOrigin as error:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    try:
        apply_rate_limits(request)
    except RateLimitExceeded as error:
        return JSONResponse(
            status_code=429,
            content={"detail": "too many requests"},
            headers={"Retry-After": str(error.retry_after)},
        )
    except RateLimiterUnavailable:
        if request.method == "POST" and (
            path == "/auth/login" or path.startswith("/heartbeats/")
        ):
            return JSONResponse(
                status_code=503,
                content={"detail": "request protection temporarily unavailable"},
                headers={"Retry-After": "5"},
            )

    if request.method == "OPTIONS" or path in PUBLIC_PATHS or path.startswith("/heartbeats/"):
        return await call_next(request)
    user = session_user(request.cookies.get(COOKIE_NAME))
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "authentication required"})
    request.state.user = user
    return await call_next(request)


@app.post("/auth/login")
def post_login(credentials: LoginRequest, response: Response):
    token = login(credentials.email, credentials.password)
    if token is None:
        raise HTTPException(status_code=401, detail="invalid email or password")
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="strict",
        secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        max_age=7 * 24 * 60 * 60, path="/",
    )
    return {"status": "ok"}


@app.get("/auth/me")
def get_me(request: Request):
    return request.state.user


@app.get("/backups/summary")
def backup_summary():
    return get_backup_summary()


@app.post("/auth/logout", status_code=204)
def post_logout(request: Request, response: Response):
    logout(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")


def component_status(last_seen_value, stale_after_seconds=30):
    if last_seen_value is None:
        return {"status": "DOWN", "last_seen_at": None, "detail": "No recent signal"}

    last_seen = float(last_seen_value)
    age_seconds = max(0, round(time.time() - last_seen))
    return {
        "status": "UP" if age_seconds <= stale_after_seconds else "DOWN",
        "last_seen_at": datetime.fromtimestamp(last_seen, tz=timezone.utc),
        "detail": f"Latest signal {age_seconds} s ago",
    }


@app.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_project(project: ProjectCreate):
    return create_project(project.model_dump())


@app.get("/projects", response_model=list[ProjectResponse])
def get_projects():
    return list_projects()


@app.patch("/projects/{project_id}", response_model=ProjectResponse)
def patch_project(project_id: int, project: ProjectUpdate):
    changes = project.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="no changes provided")
    updated_project = update_project(project_id, changes)
    if updated_project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return updated_project


@app.post(
    "/monitors",
    response_model=MonitorCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_monitor(monitor: MonitorCreate):
    data = monitor.model_dump(mode="json")
    heartbeat_token = None
    if monitor.monitor_type == "HEARTBEAT":
        heartbeat_token = secrets.token_urlsafe(32)
        data["heartbeat_token_hash"] = hashlib.sha256(
            heartbeat_token.encode()
        ).hexdigest()
    created_monitor = create_monitor(data)
    return {**created_monitor, "heartbeat_token": heartbeat_token}


@app.get("/monitors", response_model=list[MonitorResponse])
def get_monitors():
    return list_monitors()


@app.get("/dashboard", response_model=list[DashboardMonitorResponse])
def get_dashboard():
    return list_dashboard_monitors()


@app.get(
    "/monitors/{monitor_id}/history",
    response_model=MonitorHistoryResponse,
)
def get_history(monitor_id: int, hours: int = Query(default=24)):
    if hours not in {24, 168, 720}:
        raise HTTPException(status_code=400, detail="hours must be 24, 168 or 720")
    history = get_monitor_history(monitor_id, hours)
    if history is None:
        raise HTTPException(status_code=404, detail="monitor not found")
    return history


@app.patch("/monitors/{monitor_id}", response_model=MonitorResponse)
def patch_monitor(monitor_id: int, monitor: MonitorUpdate):
    changes = monitor.model_dump(exclude_unset=True, mode="json")
    if not changes:
        raise HTTPException(status_code=400, detail="no changes provided")
    if changes.get("is_archived") is True:
        changes["is_active"] = False

    updated_monitor = update_monitor(monitor_id, changes)
    if updated_monitor is None:
        raise HTTPException(status_code=404, detail="monitor not found")
    return updated_monitor


@app.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_monitor(monitor_id: int):
    if not delete_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="monitor not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/monitors/{monitor_id}/check",
    response_model=CheckResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_check(monitor_id: int):
    monitor = get_monitor(monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="monitor not found")
    if not monitor["is_active"]:
        raise HTTPException(status_code=409, detail="monitor is inactive")
    if monitor["project_is_archived"]:
        raise HTTPException(status_code=409, detail="project is archived")
    if monitor["monitor_type"] != "HTTP":
        raise HTTPException(status_code=409, detail="monitor is not HTTP")

    result = check_url(
        url=monitor["url"],
        timeout_seconds=monitor["timeout_seconds"],
        expected_status_code=monitor["expected_status_code"],
    )
    result["monitor_id"] = monitor_id
    return create_check(result)


@app.get(
    "/monitors/{monitor_id}/checks",
    response_model=list[CheckResponse],
)
def get_checks(monitor_id: int):
    if get_monitor(monitor_id) is None:
        raise HTTPException(status_code=404, detail="monitor not found")
    return list_checks(monitor_id)


@app.get("/incidents", response_model=list[IncidentResponse])
def get_incidents():
    return list_incidents()


@app.post("/heartbeats/{token}", status_code=status.HTTP_204_NO_CONTENT)
def post_heartbeat(token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if record_heartbeat(token_hash) is None:
        raise HTTPException(status_code=404, detail="heartbeat not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/monitors/{monitor_id}/heartbeat-token",
    response_model=HeartbeatTokenResponse,
)
def rotate_token(monitor_id: int):
    heartbeat_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(heartbeat_token.encode()).hexdigest()
    result = rotate_heartbeat_token(monitor_id, token_hash)
    if result is None:
        raise HTTPException(status_code=404, detail="heartbeat monitor not found")
    return {
        "heartbeat_token": heartbeat_token,
        "rotated_at": result["heartbeat_token_rotated_at"],
    }


@app.get("/health/live")
def liveness():
    return {"status": "ok"}


@app.get("/system/health")
def system_health():
    database_started_at = time.perf_counter()
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        database = {
            "status": "UP",
            "detail": f"Response in {round((time.perf_counter() - database_started_at) * 1000, 2)} ms",
        }
    except Exception as error:
        database = {"status": "DOWN", "detail": str(error)}

    try:
        queue = get_queue_health()
        redis_status = {
            "status": "UP",
            "detail": f"Response in {queue['redis_latency_ms']} ms",
        }
        scheduler = component_status(queue["scheduler_last_seen"])
        worker = component_status(queue["worker_last_seen"])
        queue_status = {
            "status": "UP",
            "detail": f"{queue['stream_jobs']} queued · {queue['pending_jobs']} processing",
            "stream_jobs": queue["stream_jobs"],
            "pending_jobs": queue["pending_jobs"],
        }
    except Exception as error:
        redis_status = {"status": "DOWN", "detail": str(error)}
        scheduler = {"status": "UNKNOWN", "last_seen_at": None, "detail": "Redis unavailable"}
        worker = {"status": "UNKNOWN", "last_seen_at": None, "detail": "Redis unavailable"}
        queue_status = {"status": "UNKNOWN", "detail": "Redis unavailable", "stream_jobs": None, "pending_jobs": None}

    return {
        "api": {"status": "UP", "detail": "The API responded"},
        "database": database,
        "redis": redis_status,
        "scheduler": scheduler,
        "worker": worker,
        "queue": queue_status,
        "checked_at": datetime.now(timezone.utc),
    }


@app.get("/system/health/{component}/history")
def system_component_history(component: str, hours: int = Query(default=24)):
    if component not in {"web", "api", "database", "redis", "scheduler", "worker", "queue"}:
        raise HTTPException(status_code=404, detail="component not found")
    if hours not in {24, 168, 720}:
        raise HTTPException(status_code=400, detail="hours must be 24, 168 or 720")
    return get_system_health_history(component, hours)


@app.get("/system/incidents")
def get_system_incidents():
    return list_system_incidents()


@app.get("/system/incidents/{incident_id}")
def get_system_incident_detail(incident_id: int):
    incident = get_system_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="system incident not found")
    return incident


@app.get("/notifications/summary")
def notification_summary():
    return get_notification_summary()


@app.get("/notifications/attempts")
def notification_attempts(limit: int = Query(default=30, ge=1, le=100)):
    return list_notification_attempts(limit)


@app.post("/notifications/{notification_id}/retry", status_code=202)
def retry_notification(notification_id: int):
    if not retry_failed_notification(notification_id):
        raise HTTPException(status_code=404, detail="failed notification not found")
    return {"status": "queued"}


@app.get("/health/ready")
def readiness():
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        )

    try:
        get_queue_health()
    except Exception:
        raise HTTPException(status_code=503, detail="redis unavailable")

    return {"status": "ok", "database": "ok", "redis": "ok"}
