"""Alert evaluation engine.

Lifecycle:   open -> acknowledged -> resolved   (auto-resolves when condition clears)
Storm control:
  * Duplicate suppression: one non-resolved alert per fingerprint (rule+host+subject).
    Re-triggers only bump `occurrences`/`last_triggered_at`; no new alert, no notification.
  * Cooldown: after an alert resolves, the same fingerprint cannot open a new alert until
    the rule's cooldown has elapsed (damps flapping).
  * Maintenance windows suppress new alerts for covered hosts.
  * Notification is sent once when an alert opens and once on resolution.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from . import models
from .config import Settings
from .notify import Notifier

log = logging.getLogger("infrawatch.alerts")


def host_status(host: models.Host, now: datetime, offline_after: int) -> str:
    if host.revoked:
        return "revoked"
    if host.last_seen is None:
        return "pending"  # registered but has never reported: NOT considered monitored
    return "online" if (now - host.last_seen).total_seconds() <= offline_after else "offline"


def in_maintenance(db: Session, host: models.Host, now: datetime) -> bool:
    q = select(models.MaintenanceWindow).where(
        models.MaintenanceWindow.starts_at <= now, models.MaintenanceWindow.ends_at >= now
    )
    for w in db.scalars(q):
        if w.host_id == host.id:
            return True
        if w.host_id is None and (w.environment is None or w.environment == host.environment) and (
            w.group is None or w.group == host.group
        ):
            return True
    return False


def _rule_applies(rule: models.AlertRule, host: models.Host) -> bool:
    return (
        (rule.host_id is None or rule.host_id == host.id)
        and (rule.environment is None or rule.environment == host.environment)
        and (rule.group is None or rule.group == host.group)
    )


def _sustained(db: Session, host: models.Host, now: datetime, for_seconds: int, column, predicate):
    """Return (violating, latest_value). Violating iff there is >=1 sample in the window and
    every sample in it satisfies predicate. A fresh sample must exist (not stale)."""
    window = max(for_seconds, 0)
    tol = 2 * max(host.collection_interval or 15, 1) + 5  # allow ~2 missed samples at the window edge
    rows = db.execute(
        select(models.Metric.ts, column)
        .where(models.Metric.host_id == host.id, models.Metric.ts >= now - timedelta(seconds=window + tol))
        .order_by(models.Metric.ts.desc())
    ).all()
    if not rows:
        return False, None
    latest_ts, latest_val = rows[0]
    if latest_val is None:
        return False, None
    if window:
        in_window = [(t, v) for t, v in rows if t >= now - timedelta(seconds=window)]
        # must have data covering (most of) the window, otherwise we haven't observed it long enough
        oldest_needed = now - timedelta(seconds=window)
        if rows[-1][0] > oldest_needed + timedelta(seconds=tol):
            return False, latest_val
        return bool(in_window) and all(v is not None and predicate(v) for _, v in in_window), latest_val
    return predicate(latest_val), latest_val


def _conditions(db: Session, rule: models.AlertRule, host: models.Host, now: datetime, settings: Settings):
    """Yield (subject, violated, value, title, message)."""
    t = rule.type
    if t in ("cpu_high", "mem_high"):
        col = models.Metric.cpu_percent if t == "cpu_high" else models.Metric.mem_percent
        label = "CPU" if t == "cpu_high" else "Memory"
        v, val = _sustained(db, host, now, rule.for_seconds, col, lambda x: x > rule.threshold)
        yield "", v, val, f"{label} high on {host.hostname}", (
            f"{label} utilization {val:.1f}% exceeds {rule.threshold:g}%" if val is not None else "")
    elif t == "disk_low":
        col = 100 - models.Metric.disk_percent
        v, val = _sustained(db, host, now, rule.for_seconds, col, lambda x: x < rule.threshold)
        yield "", v, val, f"Low disk space on {host.hostname}", (
            f"Free disk space {val:.1f}% is below {rule.threshold:g}%" if val is not None else "")
    elif t == "host_down":
        status = host_status(host, now, settings.offline_after_seconds)
        yield "", status == "offline", None, f"Host {host.hostname} is unavailable", (
            f"No data received since {host.last_seen.isoformat() if host.last_seen else 'never'}")
    elif t in ("service_down", "response_slow"):
        # Latest result per service on this host (within a recent window)
        rows = db.execute(
            select(models.ServiceCheck)
            .where(models.ServiceCheck.host_id == host.id, models.ServiceCheck.ts >= now - timedelta(seconds=600))
            .order_by(models.ServiceCheck.ts.desc())
        ).scalars()
        seen: dict[str, models.ServiceCheck] = {}
        for c in rows:
            seen.setdefault(c.name, c)
        for name, c in seen.items():
            if rule.service_name and rule.service_name != name:
                continue
            if t == "service_down":
                yield name, not c.ok, None, f"Service {name} down on {host.hostname}", (
                    f"{c.kind} check {c.target} failed: {c.error or 'unhealthy'}")
            else:
                slow = c.ok and c.response_ms is not None and c.response_ms > rule.threshold
                yield name, slow, c.response_ms, f"Slow response from {name} on {host.hostname}", (
                    f"Response time {c.response_ms:.0f} ms exceeds {rule.threshold:g} ms" if c.response_ms else "")


def evaluate(db: Session, settings: Settings, notifier: Notifier, now: datetime) -> dict:
    """Run all enabled rules once. Returns counters (handy for tests/metrics)."""
    stats = {"opened": 0, "suppressed": 0, "resolved": 0, "cooldown": 0, "maintenance": 0}
    hosts = db.scalars(select(models.Host).where(models.Host.revoked.is_(False))).all()
    rules = db.scalars(select(models.AlertRule).where(models.AlertRule.enabled.is_(True))).all()
    channels = db.scalars(select(models.NotificationChannel).where(models.NotificationChannel.enabled.is_(True))).all()
    active_fps: set[str] = set()
    evaluated_fps: set[str] = set()

    def notify(event: str, alert: models.Alert) -> None:
        for ch in channels:
            notifier.send(ch, event, alert)

    for rule in rules:
        for host in hosts:
            if not _rule_applies(rule, host):
                continue
            # A host that has never reported has no data: nothing to evaluate.
            if host.last_seen is None:
                continue
            for subject, violated, value, title, message in _conditions(db, rule, host, now, settings):
                fp = f"{rule.id}:{host.id}:{subject}"
                evaluated_fps.add(fp)
                existing = db.scalars(
                    select(models.Alert).where(models.Alert.fingerprint == fp, models.Alert.status != "resolved")
                ).first()
                if violated:
                    active_fps.add(fp)
                    if existing:
                        existing.occurrences += 1
                        existing.last_triggered_at = now
                        existing.value = value
                        stats["suppressed"] += 1
                        continue
                    if in_maintenance(db, host, now):
                        stats["maintenance"] += 1
                        continue
                    last = db.scalars(
                        select(models.Alert).where(models.Alert.fingerprint == fp, models.Alert.status == "resolved")
                        .order_by(models.Alert.resolved_at.desc())
                    ).first()
                    if last and last.resolved_at and (now - last.resolved_at).total_seconds() < rule.cooldown_seconds:
                        stats["cooldown"] += 1
                        continue
                    alert = models.Alert(
                        rule_id=rule.id, host_id=host.id, fingerprint=fp, severity=rule.severity, title=title,
                        message=message, value=value, opened_at=now, last_triggered_at=now, host=host,
                    )
                    db.add(alert)
                    db.flush()
                    stats["opened"] += 1
                    notify("alert.opened", alert)
                    alert.notified_at = now
                elif existing:
                    _resolve(existing, "system", now)
                    stats["resolved"] += 1
                    notify("alert.resolved", existing)

    # Auto-resolve open alerts whose rule was disabled/deleted or whose subject vanished (e.g. service removed).
    for alert in db.scalars(select(models.Alert).where(models.Alert.status != "resolved")).all():
        if alert.fingerprint in evaluated_fps:
            continue
        rule = db.get(models.AlertRule, alert.rule_id) if alert.rule_id else None
        host = alert.host
        stale = rule is None or not rule.enabled or host.revoked
        if not stale and rule.type in ("service_down", "response_slow"):
            stale = True  # service no longer reporting within the window
        if stale:
            _resolve(alert, "system", now)
            stats["resolved"] += 1
    db.commit()
    return stats


def _resolve(alert: models.Alert, by: str, now: datetime) -> None:
    alert.status = "resolved"
    alert.resolved_by = by
    alert.resolved_at = now
