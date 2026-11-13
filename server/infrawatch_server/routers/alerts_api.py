from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..alerts import _resolve
from ..deps import Principal, audit, client_ip, current_user, get_db, require_role
from ..models import utcnow

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def alert_dict(a: models.Alert) -> dict:
    return {
        "id": a.id, "rule_id": a.rule_id, "host_id": a.host_id, "hostname": a.host.hostname,
        "environment": a.host.environment, "is_simulated": a.host.is_simulated, "severity": a.severity,
        "title": a.title, "message": a.message, "status": a.status, "value": a.value, "occurrences": a.occurrences,
        "opened_at": a.opened_at, "last_triggered_at": a.last_triggered_at, "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": a.acknowledged_at, "resolved_by": a.resolved_by, "resolved_at": a.resolved_at,
    }


@router.get("")
def list_alerts(status: str | None = Query(None, pattern="^(open|acknowledged|resolved|active)$"),
                severity: str | None = Query(None, pattern="^(info|warning|critical)$"), host_id: int | None = None,
                include_simulated: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                _: Principal = Depends(current_user), db: Session = Depends(get_db)):
    q = select(models.Alert).join(models.Host)
    if not include_simulated:
        q = q.where(models.Host.is_simulated.is_(False))
    if status == "active":
        q = q.where(models.Alert.status != "resolved")
    elif status:
        q = q.where(models.Alert.status == status)
    if severity:
        q = q.where(models.Alert.severity == severity)
    if host_id:
        q = q.where(models.Alert.host_id == host_id)
    q = q.order_by(models.Alert.opened_at.desc()).limit(limit).offset(offset)
    return [alert_dict(a) for a in db.scalars(q).unique()]


def _get(db: Session, alert_id: int) -> models.Alert:
    a = db.get(models.Alert, alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    return a


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: int, request: Request, p: Principal = Depends(require_role("operator")),
                db: Session = Depends(get_db)):
    a = _get(db, alert_id)
    if a.status != "open":
        raise HTTPException(409, f"alert is {a.status}; only open alerts can be acknowledged")
    a.status, a.acknowledged_by, a.acknowledged_at = "acknowledged", p.username, utcnow()
    audit(db, p.username, "alert.acknowledge", f"alert:{a.id}", client_ip(request))
    db.commit()
    return alert_dict(a)


@router.post("/{alert_id}/resolve")
def resolve(alert_id: int, request: Request, p: Principal = Depends(require_role("operator")),
            db: Session = Depends(get_db)):
    a = _get(db, alert_id)
    if a.status == "resolved":
        raise HTTPException(409, "alert already resolved")
    _resolve(a, p.username, utcnow())
    audit(db, p.username, "alert.resolve", f"alert:{a.id}", client_ip(request))
    db.commit()
    return alert_dict(a)
