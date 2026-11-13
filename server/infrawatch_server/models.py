from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, TypeDecorator, BigInteger,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class UTCDateTime(TypeDecorator):
    """Always store/return timezone-aware UTC datetimes (SQLite drops tzinfo otherwise)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


ROLES = ("viewer", "operator", "admin")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EnrollmentToken(Base):
    """One-time, expiring token an agent uses to register itself."""

    __tablename__ = "enrollment_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    environment: Mapped[str] = mapped_column(String(64), default="production")
    group: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    used_by_host_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Host(Base):
    __tablename__ = "hosts"
    id: Mapped[int] = mapped_column(primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255))
    os: Mapped[str] = mapped_column(String(64), default="")
    os_version: Mapped[str] = mapped_column(String(255), default="")
    arch: Mapped[str] = mapped_column(String(32), default="")
    agent_version: Mapped[str] = mapped_column(String(32), default="")
    environment: Mapped[str] = mapped_column(String(64), default="production", index=True)
    group: Mapped[str] = mapped_column(String(64), default="", index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Only ever set by a successfully authenticated ingest request.
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    collection_interval: Mapped[int] = mapped_column(Integer, default=15)


class Metric(Base):
    __tablename__ = "metrics"
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, primary_key=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    mem_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    mem_available_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mem_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_free_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    net_sent_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_recv_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    load1: Mapped[float | None] = mapped_column(Float, nullable=True)
    load5: Mapped[float | None] = mapped_column(Float, nullable=True)
    load15: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_metrics_ts", "ts"),)


class ServiceCheck(Base):
    __tablename__ = "service_checks"
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="http")  # http | tcp | process
    target: Mapped[str] = mapped_column(String(512), default="")
    ok: Mapped[bool] = mapped_column(Boolean)
    response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(String(255), default="")

    __table_args__ = (Index("ix_checks_ts", "ts"),)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(16), default="webhook")
    url: Mapped[str] = mapped_column(String(1024))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_severity: Mapped[str] = mapped_column(String(16), default="warning")


RULE_TYPES = ("cpu_high", "mem_high", "disk_low", "host_down", "service_down", "response_slow")
SEVERITIES = ("info", "warning", "critical")


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(32))
    # cpu_high/mem_high: percent above. disk_low: free percent below. response_slow: ms above.
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    for_seconds: Mapped[int] = mapped_column(Integer, default=0)  # condition must hold this long
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Scope: all hosts if everything is null
    host_id: Mapped[int | None] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(255), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|acknowledged|resolved
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_triggered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    host: Mapped[Host] = relationship(lazy="joined")


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    host_id: Mapped[int | None] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[str] = mapped_column(String(64), default="")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(255), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
