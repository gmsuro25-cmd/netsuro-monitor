from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=500)


class MonitorCreate(BaseModel):
    project_id: int
    monitor_type: Literal["HTTP", "HEARTBEAT"] = "HTTP"
    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl | None = None
    interval_seconds: int = Field(default=300, ge=30)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    expected_status_code: int = Field(default=200, ge=100, le=599)
    heartbeat_grace_seconds: int = Field(default=30, ge=0, le=3600)

    @model_validator(mode="after")
    def validate_type_fields(self):
        if self.monitor_type == "HTTP" and self.url is None:
            raise ValueError("url is required for HTTP monitors")
        return self


class MonitorResponse(MonitorCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_archived: bool
    current_status: str
    consecutive_failures: int
    consecutive_successes: int
    last_heartbeat_at: datetime | None
    heartbeat_token_rotated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MonitorUpdate(BaseModel):
    project_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: HttpUrl | None = None
    interval_seconds: int | None = Field(default=None, ge=30)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    expected_status_code: int | None = Field(default=None, ge=100, le=599)
    heartbeat_grace_seconds: int | None = Field(default=None, ge=0, le=3600)
    is_active: bool | None = None
    is_archived: bool | None = None


class CheckResponse(BaseModel):
    id: int
    monitor_id: int
    status_code: int | None
    response_time_ms: int
    succeeded: bool
    error_message: str | None
    checked_at: datetime


class IncidentResponse(BaseModel):
    id: int
    monitor_id: int
    started_at: datetime
    resolved_at: datetime | None
    opening_check_id: int
    closing_check_id: int | None


class DashboardMonitorResponse(MonitorResponse):
    latest_status_code: int | None
    latest_response_time_ms: int | None
    latest_succeeded: bool | None
    latest_checked_at: datetime | None


class MonitorCreatedResponse(MonitorResponse):
    heartbeat_token: str | None = None


class HeartbeatTokenResponse(BaseModel):
    heartbeat_token: str
    rotated_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_archived: bool | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    is_archived: bool
    current_status: str
    monitor_count: int
    created_at: datetime
    updated_at: datetime


class HistorySummary(BaseModel):
    total_checks: int
    success_rate: float
    failures: int
    avg_response_time_ms: float | None


class HistoryPoint(BaseModel):
    bucket: datetime
    availability: float
    avg_response_time_ms: float | None
    checks: int


class MonitorHistoryResponse(BaseModel):
    monitor: MonitorResponse
    summary: HistorySummary
    points: list[HistoryPoint]
    recent_checks: list[CheckResponse]
    incidents: list[IncidentResponse]
