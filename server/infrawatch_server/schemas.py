from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Name = Field(min_length=1, max_length=128)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- agent protocol -------------------------------------------------------
class RegisterRequest(Strict):
    hostname: str = Field(min_length=1, max_length=255)
    os: str = Field(default="", max_length=64)
    os_version: str = Field(default="", max_length=255)
    arch: str = Field(default="", max_length=32)
    agent_version: str = Field(default="", max_length=32)


class RegisterResponse(BaseModel):
    host_id: int
    api_key: str
    environment: str
    note: str = "Store this key securely; it is shown only once."


class SystemMetrics(Strict):
    cpu_percent: float | None = Field(None, ge=0, le=100)
    mem_percent: float | None = Field(None, ge=0, le=100)
    mem_available_bytes: int | None = Field(None, ge=0)
    mem_total_bytes: int | None = Field(None, ge=0)
    disk_percent: float | None = Field(None, ge=0, le=100)
    disk_free_bytes: int | None = Field(None, ge=0)
    disk_total_bytes: int | None = Field(None, ge=0)
    net_sent_bps: float | None = Field(None, ge=0)
    net_recv_bps: float | None = Field(None, ge=0)
    uptime_seconds: int | None = Field(None, ge=0)
    load1: float | None = Field(None, ge=0)  # None where unsupported (Windows)
    load5: float | None = Field(None, ge=0)
    load15: float | None = Field(None, ge=0)


class CheckResult(Strict):
    name: str = Field(min_length=1, max_length=128)
    kind: Literal["http", "tcp", "process"] = "http"
    target: str = Field(default="", max_length=512)
    ok: bool
    response_ms: float | None = Field(None, ge=0, le=3_600_000)
    status_code: int | None = Field(None, ge=100, le=599)
    error: str = Field(default="", max_length=255)


class Sample(Strict):
    ts: datetime  # must be timezone-aware
    system: SystemMetrics
    checks: list[CheckResult] = Field(default_factory=list)

    @field_validator("ts")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts must include a timezone")
        return v


class AgentInfo(Strict):
    hostname: str | None = Field(None, min_length=1, max_length=255)
    os: str | None = Field(None, max_length=64)
    os_version: str | None = Field(None, max_length=255)
    arch: str | None = Field(None, max_length=32)
    agent_version: str | None = Field(None, max_length=32)
    collection_interval: int | None = Field(None, ge=1, le=86400)


class IngestRequest(Strict):
    agent: AgentInfo = Field(default_factory=AgentInfo)
    samples: list[Sample] = Field(min_length=1)


class IngestResponse(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    latest_agent_version: str
    upgrade_available: bool


# ---- dashboard API --------------------------------------------------------
class LoginRequest(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(Strict):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=256)
    role: Literal["viewer", "operator", "admin"] = "viewer"


class UserUpdate(Strict):
    role: Literal["viewer", "operator", "admin"] | None = None
    disabled: bool | None = None
    password: str | None = Field(None, min_length=10, max_length=256)


class EnrollmentCreate(Strict):
    label: str = Field(default="", max_length=128)
    environment: str = Field(default="production", min_length=1, max_length=64)
    group: str = Field(default="", max_length=64)
    ttl_minutes: int = Field(default=60, ge=1, le=7 * 24 * 60)


class HostUpdate(Strict):
    environment: str | None = Field(None, min_length=1, max_length=64)
    group: str | None = Field(None, max_length=64)
    revoked: bool | None = None


class RuleIn(Strict):
    name: str = Name
    type: Literal["cpu_high", "mem_high", "disk_low", "host_down", "service_down", "response_slow"]
    threshold: float | None = Field(None, ge=0)
    for_seconds: int = Field(default=0, ge=0, le=86400)
    severity: Literal["info", "warning", "critical"] = "warning"
    cooldown_seconds: int = Field(default=300, ge=0, le=7 * 86400)
    enabled: bool = True
    host_id: int | None = None
    environment: str | None = Field(None, max_length=64)
    group: str | None = Field(None, max_length=64)
    service_name: str | None = Field(None, max_length=128)

    @field_validator("threshold")
    @classmethod
    def _noop(cls, v):
        return v

    def model_post_init(self, _ctx) -> None:
        needs = {"cpu_high", "mem_high", "disk_low", "response_slow"}
        if self.type in needs and self.threshold is None:
            raise ValueError(f"threshold is required for {self.type}")
        if self.type in ("cpu_high", "mem_high", "disk_low") and (self.threshold or 0) > 100:
            raise ValueError("percent thresholds must be <= 100")


class ChannelIn(Strict):
    name: str = Name
    url: str = Field(min_length=8, max_length=1024)
    enabled: bool = True
    min_severity: Literal["info", "warning", "critical"] = "warning"


class MaintenanceIn(Strict):
    name: str = Name
    host_id: int | None = None
    environment: str | None = Field(None, max_length=64)
    group: str | None = Field(None, max_length=64)
    starts_at: datetime
    ends_at: datetime

    def model_post_init(self, _ctx) -> None:
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
