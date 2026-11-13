from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..alerts import host_status
from ..deps import Principal, audit, client_ip, current_user, get_db, require_role
from ..models import utcnow

router = APIRouter(prefix="/api/v1", tags=["hosts"])

RANGES = {"15m": 900, "1h": 3600, "6h": 6 * 3600, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}
METRIC_FIELDS = ["cpu_percent", "mem_percent", "mem_available_bytes", "disk_percent", "disk_free_bytes",
                 "net_sent_bps", "net_recv_bps", "uptime_seconds", "load1", "load5", "load15"]


def host_dict(h: models.Host, now: datetime, offline_after: int, latest: models.Metric | None = None,
              open_alerts: int = 0, min_version: str = "") -> dict:
    d = {
        "id": h.id, "hostname": h.hostname, "os": h.os, "os_version": h.os_version, "arch": h.arch,
        "agent_version": h.agent_version, "environment": h.environment, "group": h.group,
        "status": host_status(h, now, offline_after), "last_seen": h.last_seen, "registered_at": h.registered_at,
        "is_simulated": h.is_simulated, "open_alerts": open_alerts, "collection_interval": h.collection_interval,
    }
    if latest:
        d["latest"] = {f: getattr(latest, f) for f in METRIC_FIELDS} | {"ts": latest.ts}
    return d


def _filters(q, include_simulated: bool, environment: str | None, group: str | None):
    if not include_simulated:
        q = q.where(models.Host.is_simulated.is_(False))
    if environment:
        q = q.where(models.Host.environment == environment)
    if group:
        q = q.where(models.Host.group == group)
    return q


def _latest_metrics(db: Session, host_ids: list[int]) -> dict[int, models.Metric]:
    if not host_ids:
        return {}
    sub = (select(models.Metric.host_id, func.max(models.Metric.ts).label("mts"))
           .where(models.Metric.host_id.in_(host_ids)).group_by(models.Metric.host_id).subquery())
    rows = db.scalars(select(models.Metric).join(
        sub, (models.Metric.host_id == sub.c.host_id) & (models.Metric.ts == sub.c.mts)))
    return {m.host_id: m for m in rows}


@router.get("/hosts")
def list_hosts(request: Request, include_simulated: bool = False, environment: str | None = None,
               group: str | None = None, status: str | None = None, search: str | None = Query(None, max_length=100),
               _: Principal = Depends(current_user), db: Session = Depends(get_db)):
    s = request.app.state.settings
    now = utcnow()
    q = _filters(select(models.Host), include_simulated, environment, group).order_by(models.Host.hostname)
    if search:
        q = q.where(models.Host.hostname.ilike(f"%{search}%"))
    hosts = db.scalars(q).all()
    latest = _latest_metrics(db, [h.id for h in hosts])
    counts = dict(db.execute(select(models.Alert.host_id, func.count()).where(models.Alert.status != "resolved")
                             .group_by(models.Alert.host_id)).all())
    out = [host_dict(h, now, s.offline_after_seconds, latest.get(h.id), counts.get(h.id, 0)) for h in hosts]
    if status:
        out = [h for h in out if h["status"] == status]
    return out


@router.get("/overview")
def overview(request: Request, include_simulated: bool = False, environment: str | None = None,
             _: Principal = Depends(current_user), db: Session = Depends(get_db)):
    s = request.app.state.settings
    now = utcnow()
    hosts = db.scalars(_filters(select(models.Host), include_simulated, environment, None)).all()
    ids = [h.id for h in hosts]
    statuses = [host_status(h, now, s.offline_after_seconds) for h in hosts]
    alert_q = select(models.Alert).where(models.Alert.status != "resolved", models.Alert.host_id.in_(ids or [0]))
    open_alerts = db.scalars(alert_q).all()
    attention_ids = {a.host_id for a in open_alerts} | {h.id for h, st in zip(hosts, statuses) if st == "offline"}
    latest = _latest_metrics(db, ids)

    def avg(field):
        vals = [getattr(latest[h.id], field) for h, st in zip(hosts, statuses)
                if st == "online" and h.id in latest and getattr(latest[h.id], field) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    svc_since = now - timedelta(minutes=10)
    svc = db.execute(select(models.ServiceCheck.host_id, models.ServiceCheck.name, models.ServiceCheck.ok,
                            models.ServiceCheck.ts).where(models.ServiceCheck.host_id.in_(ids or [0]),
                            models.ServiceCheck.ts >= svc_since).order_by(models.ServiceCheck.ts.desc())).all()
    latest_svc: dict[tuple[int, str], bool] = {}
    for hid, name, ok, _ts in svc:
        latest_svc.setdefault((hid, name), ok)
    return {
        "total": len(hosts), "online": statuses.count("online"), "offline": statuses.count("offline"),
        "pending": statuses.count("pending"), "needs_attention": len(attention_ids),
        "open_alerts": len(open_alerts),
        "critical_alerts": sum(1 for a in open_alerts if a.severity == "critical"),
        "avg_cpu": avg("cpu_percent"), "avg_mem": avg("mem_percent"), "avg_disk": avg("disk_percent"),
        "services_up": sum(latest_svc.values()), "services_total": len(latest_svc),
        "environments": sorted({h.environment for h in hosts}),
    }


def _get_host(db: Session, host_id: int) -> models.Host:
    h = db.get(models.Host, host_id)
    if not h:
        raise HTTPException(404, "host not found")
    return h


@router.get("/hosts/{host_id}")
def get_host(host_id: int, request: Request, _: Principal = Depends(current_user), db: Session = Depends(get_db)):
    h = _get_host(db, host_id)
    s = request.app.state.settings
    latest = _latest_metrics(db, [h.id]).get(h.id)
    n = db.scalar(select(func.count()).select_from(models.Alert).where(
        models.Alert.host_id == h.id, models.Alert.status != "resolved"))
    d = host_dict(h, utcnow(), s.offline_after_seconds, latest, n)
    d["agent_outdated"] = bool(h.agent_version) and h.agent_version != s.latest_agent_version
    return d


@router.patch("/hosts/{host_id}")
def update_host(host_id: int, body: schemas.HostUpdate, request: Request, p: Principal = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    h = _get_host(db, host_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(h, k, v)
    audit(db, p.username, "host.update", f"host:{h.id}", client_ip(request), **changes)
    db.commit()
    return host_dict(h, utcnow(), request.app.state.settings.offline_after_seconds)


@router.delete("/hosts/{host_id}", status_code=204)
def delete_host(host_id: int, request: Request, p: Principal = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    h = _get_host(db, host_id)
    audit(db, p.username, "host.delete", f"host:{h.id}", client_ip(request), hostname=h.hostname)
    db.delete(h)
    db.commit()


def _range(range_: str, start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    end = end or utcnow()
    if start is None:
        if range_ not in RANGES:
            raise HTTPException(422, f"range must be one of {sorted(RANGES)}")
        start = end - timedelta(seconds=RANGES[range_])
    if start >= end:
        raise HTTPException(422, "start must be before end")
    if (end - start) > timedelta(days=90):
        raise HTTPException(422, "window too large (max 90 days)")
    return start, end


def _bucketed(rows: list[models.Metric], start: datetime, end: datetime, max_points: int) -> list[dict]:
    """Downsample by averaging into at most max_points time buckets (DB-agnostic)."""
    span = (end - start).total_seconds()
    size = max(1, int(span / max_points))
    buckets: dict[int, list[models.Metric]] = {}
    for m in rows:
        buckets.setdefault(int((m.ts - start).total_seconds() // size), []).append(m)
    out = []
    for k in sorted(buckets):
        ms = buckets[k]
        point = {"ts": start + timedelta(seconds=k * size)}
        for f in METRIC_FIELDS:
            vals = [getattr(m, f) for m in ms if getattr(m, f) is not None]
            point[f] = round(sum(vals) / len(vals), 3) if vals else None
        out.append(point)
    return out


@router.get("/hosts/{host_id}/metrics")
def host_metrics(host_id: int, range: str = "1h", start: datetime | None = None, end: datetime | None = None,
                 max_points: int = Query(300, ge=10, le=2000), _: Principal = Depends(current_user),
                 db: Session = Depends(get_db)):
    _get_host(db, host_id)
    a, b = _range(range, start, end)
    rows = db.scalars(select(models.Metric).where(models.Metric.host_id == host_id, models.Metric.ts >= a,
                                                  models.Metric.ts <= b).order_by(models.Metric.ts)).all()
    return {"start": a, "end": b, "points": _bucketed(rows, a, b, max_points)}


@router.get("/hosts/{host_id}/metrics/export")
def export_metrics(host_id: int, request: Request, format: Literal["csv", "json"] = "csv", range: str = "24h",
                   start: datetime | None = None, end: datetime | None = None,
                   p: Principal = Depends(current_user), db: Session = Depends(get_db)):
    h = _get_host(db, host_id)
    a, b = _range(range, start, end)
    rows = db.scalars(select(models.Metric).where(models.Metric.host_id == host_id, models.Metric.ts >= a,
                                                  models.Metric.ts <= b).order_by(models.Metric.ts).limit(200_000)).all()
    data = [{"ts": m.ts.isoformat(), **{f: getattr(m, f) for f in METRIC_FIELDS}} for m in rows]
    audit(db, p.username, "metrics.export", f"host:{h.id}", client_ip(request), rows=len(data))
    db.commit()
    fname = f"infrawatch-{h.hostname}-{a:%Y%m%d%H%M}.{format}".replace("/", "_")
    if format == "json":
        import json
        return Response(json.dumps(data), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["ts", *METRIC_FIELDS])
    w.writeheader()
    w.writerows(data)
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/hosts/{host_id}/services")
def host_services(host_id: int, range: str = "24h", _: Principal = Depends(current_user), db: Session = Depends(get_db)):
    """Current status, availability % over the range and recent history per service."""
    _get_host(db, host_id)
    a, b = _range(range, None, None)
    rows = db.scalars(select(models.ServiceCheck).where(
        models.ServiceCheck.host_id == host_id, models.ServiceCheck.ts >= a).order_by(models.ServiceCheck.ts)).all()
    by: dict[str, list[models.ServiceCheck]] = {}
    for c in rows:
        by.setdefault(c.name, []).append(c)
    out = []
    for name, cs in sorted(by.items()):
        last = cs[-1]
        ok_n = sum(1 for c in cs if c.ok)
        times = [c.response_ms for c in cs if c.ok and c.response_ms is not None]
        out.append({
            "name": name, "kind": last.kind, "target": last.target, "ok": last.ok, "last_checked": last.ts,
            "error": last.error, "availability_percent": round(100 * ok_n / len(cs), 2), "checks": len(cs),
            "failed_checks": len(cs) - ok_n, "avg_response_ms": round(sum(times) / len(times), 1) if times else None,
            "history": [{"ts": c.ts, "ok": c.ok, "response_ms": c.response_ms} for c in cs[-120:]],
        })
    return out


@router.get("/reports/summary")
def report_summary(request: Request, range: str = "7d", environment: str | None = None,
                   include_simulated: bool = False, _: Principal = Depends(current_user), db: Session = Depends(get_db)):
    a, b = _range(range, None, None)
    hosts = db.scalars(_filters(select(models.Host), include_simulated, environment, None)
                       .order_by(models.Host.hostname)).all()
    out = []
    for h in hosts:
        agg = db.execute(select(func.count(), func.avg(models.Metric.cpu_percent), func.max(models.Metric.cpu_percent),
                                func.avg(models.Metric.mem_percent), func.max(models.Metric.mem_percent),
                                func.max(models.Metric.disk_percent)).where(
            models.Metric.host_id == h.id, models.Metric.ts >= a)).one()
        n_alerts = db.scalar(select(func.count()).select_from(models.Alert).where(
            models.Alert.host_id == h.id, models.Alert.opened_at >= a))
        interval = max(h.collection_interval or 15, 1)
        expected = max(1, int((b - max(a, h.registered_at)).total_seconds() / interval))
        r = lambda v: round(v, 1) if v is not None else None  # noqa: E731
        out.append({"host_id": h.id, "hostname": h.hostname, "environment": h.environment, "samples": agg[0],
                    "avg_cpu": r(agg[1]), "max_cpu": r(agg[2]), "avg_mem": r(agg[3]), "max_mem": r(agg[4]),
                    "max_disk": r(agg[5]), "alerts": n_alerts,
                    "availability_percent": round(min(100.0, 100 * agg[0] / expected), 2)})
    return {"start": a, "end": b, "hosts": out}
