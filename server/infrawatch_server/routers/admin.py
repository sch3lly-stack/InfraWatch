from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import Principal, audit, client_ip, current_user, get_db, require_role
from ..models import utcnow
from ..notify import validate_webhook_url
from ..security import hash_password, new_secret, sha256_hex

router = APIRouter(prefix="/api/v1", tags=["admin"])


def row(o, *skip) -> dict:
    return {c.name: getattr(o, c.name) for c in o.__table__.columns if c.name not in skip}


# ---- alert rules ----------------------------------------------------------
@router.get("/rules")
def list_rules(_: Principal = Depends(current_user), db: Session = Depends(get_db)):
    return [row(r) for r in db.scalars(select(models.AlertRule).order_by(models.AlertRule.id))]


@router.post("/rules", status_code=201)
def create_rule(body: schemas.RuleIn, request: Request, p: Principal = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    if body.host_id and not db.get(models.Host, body.host_id):
        raise HTTPException(422, "unknown host_id")
    r = models.AlertRule(**body.model_dump())
    db.add(r)
    db.flush()
    audit(db, p.username, "rule.create", f"rule:{r.id}", client_ip(request), name=r.name)
    db.commit()
    return row(r)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: schemas.RuleIn, request: Request, p: Principal = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    r = db.get(models.AlertRule, rule_id)
    if not r:
        raise HTTPException(404, "rule not found")
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit(db, p.username, "rule.update", f"rule:{r.id}", client_ip(request))
    db.commit()
    return row(r)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, request: Request, p: Principal = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    r = db.get(models.AlertRule, rule_id)
    if not r:
        raise HTTPException(404, "rule not found")
    audit(db, p.username, "rule.delete", f"rule:{r.id}", client_ip(request))
    db.delete(r)
    db.commit()


# ---- notification channels ------------------------------------------------
@router.get("/channels")
def list_channels(_: Principal = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return [row(c) for c in db.scalars(select(models.NotificationChannel))]


@router.post("/channels", status_code=201)
def create_channel(body: schemas.ChannelIn, request: Request, p: Principal = Depends(require_role("admin")),
                   db: Session = Depends(get_db)):
    try:
        validate_webhook_url(body.url, request.app.state.settings.allow_private_webhooks)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    c = models.NotificationChannel(kind="webhook", **body.model_dump())
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "a channel with that name exists")
    audit(db, p.username, "channel.create", f"channel:{c.id}", client_ip(request), name=c.name)
    db.commit()
    return row(c)


@router.delete("/channels/{channel_id}", status_code=204)
def delete_channel(channel_id: int, request: Request, p: Principal = Depends(require_role("admin")),
                   db: Session = Depends(get_db)):
    c = db.get(models.NotificationChannel, channel_id)
    if not c:
        raise HTTPException(404, "channel not found")
    audit(db, p.username, "channel.delete", f"channel:{c.id}", client_ip(request))
    db.delete(c)
    db.commit()


# ---- maintenance windows --------------------------------------------------
@router.get("/maintenance")
def list_maintenance(_: Principal = Depends(current_user), db: Session = Depends(get_db)):
    return [row(m) for m in db.scalars(select(models.MaintenanceWindow).order_by(models.MaintenanceWindow.starts_at.desc()))]


@router.post("/maintenance", status_code=201)
def create_maintenance(body: schemas.MaintenanceIn, request: Request, p: Principal = Depends(require_role("operator")),
                       db: Session = Depends(get_db)):
    m = models.MaintenanceWindow(created_by=p.username, **body.model_dump())
    db.add(m)
    db.flush()
    audit(db, p.username, "maintenance.create", f"maintenance:{m.id}", client_ip(request), name=m.name)
    db.commit()
    return row(m)


@router.delete("/maintenance/{mid}", status_code=204)
def delete_maintenance(mid: int, request: Request, p: Principal = Depends(require_role("operator")),
                       db: Session = Depends(get_db)):
    m = db.get(models.MaintenanceWindow, mid)
    if not m:
        raise HTTPException(404, "not found")
    audit(db, p.username, "maintenance.delete", f"maintenance:{mid}", client_ip(request))
    db.delete(m)
    db.commit()


# ---- enrollment tokens ----------------------------------------------------
@router.get("/enrollment-tokens")
def list_tokens(_: Principal = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return [row(t, "token_hash") for t in db.scalars(select(models.EnrollmentToken).order_by(models.EnrollmentToken.id.desc()))]


@router.post("/enrollment-tokens", status_code=201)
def create_token(body: schemas.EnrollmentCreate, request: Request, p: Principal = Depends(require_role("admin")),
                 db: Session = Depends(get_db)):
    secret = "iwe_" + new_secret(24)
    t = models.EnrollmentToken(token_hash=sha256_hex(secret), label=body.label, environment=body.environment,
                               group=body.group, expires_at=utcnow() + timedelta(minutes=body.ttl_minutes),
                               created_by=p.username)
    db.add(t)
    db.flush()
    audit(db, p.username, "enrollment.create", f"token:{t.id}", client_ip(request), environment=body.environment)
    db.commit()
    return {**row(t, "token_hash"), "token": secret, "note": "shown once; single use"}


# ---- users ----------------------------------------------------------------
@router.get("/users")
def list_users(_: Principal = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return [row(u, "password_hash") for u in db.scalars(select(models.User).order_by(models.User.id))]


@router.post("/users", status_code=201)
def create_user(body: schemas.UserCreate, request: Request, p: Principal = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    u = models.User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "username already exists")
    audit(db, p.username, "user.create", f"user:{u.username}", client_ip(request), role=u.role)
    db.commit()
    return row(u, "password_hash")


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: schemas.UserUpdate, request: Request, p: Principal = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    if u.username == p.username and (body.disabled or (body.role and body.role != "admin")):
        raise HTTPException(409, "you cannot demote or disable yourself")
    if body.role is not None:
        u.role = body.role
    if body.disabled is not None:
        u.disabled = body.disabled
    if body.password:
        u.password_hash = hash_password(body.password)
    audit(db, p.username, "user.update", f"user:{u.username}", client_ip(request),
          fields=sorted(body.model_dump(exclude_unset=True)))
    db.commit()
    return row(u, "password_hash")


# ---- audit log ------------------------------------------------------------
@router.get("/audit")
def list_audit(limit: int = Query(100, ge=1, le=1000), _: Principal = Depends(require_role("admin")),
               db: Session = Depends(get_db)):
    return [row(a) for a in db.scalars(select(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(limit))]
