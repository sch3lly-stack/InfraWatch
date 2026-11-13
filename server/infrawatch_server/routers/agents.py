"""Agent-facing endpoints: registration and metric ingestion."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..alerts import host_status
from ..deps import audit, authenticated_host, client_ip, get_db, _bearer
from ..models import utcnow
from ..security import make_agent_key, new_secret, sha256_hex
from ..versioning import version_tuple

router = APIRouter(prefix="/api/v1/agents", tags=["agent"])


@router.post("/register", response_model=schemas.RegisterResponse, status_code=201)
def register(body: schemas.RegisterRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    request.app.state.limiter.check(f"register:{ip}", request.app.state.settings.rate_limit_register_per_min)
    token = _bearer(request)
    now = utcnow()
    row = db.scalars(select(models.EnrollmentToken).where(
        models.EnrollmentToken.token_hash == sha256_hex(token or ""))).first() if token else None
    if not row or row.used_at is not None or row.expires_at < now:
        audit(db, "anonymous", "agent.register_denied", ip=ip, hostname=body.hostname)
        db.commit()
        raise HTTPException(401, "invalid, used or expired enrollment token")
    secret = new_secret()
    host = models.Host(
        hostname=body.hostname, os=body.os, os_version=body.os_version, arch=body.arch,
        agent_version=body.agent_version, environment=row.environment, group=row.group,
        api_key_hash=sha256_hex(secret), registered_at=now,
    )
    db.add(host)
    db.flush()
    row.used_at, row.used_by_host_id = now, host.id  # single use
    audit(db, f"enrollment:{row.id}", "agent.registered", f"host:{host.id}", ip, hostname=body.hostname)
    db.commit()
    return schemas.RegisterResponse(host_id=host.id, api_key=make_agent_key(host.id, secret), environment=host.environment)


@router.post("/metrics", response_model=schemas.IngestResponse)
def ingest(body: schemas.IngestRequest, request: Request, host: models.Host = Depends(authenticated_host),
           db: Session = Depends(get_db)):
    s = request.app.state.settings
    if len(body.samples) > s.max_batch_samples:
        raise HTTPException(413, f"batch too large (max {s.max_batch_samples} samples)")
    now = utcnow()
    accepted = duplicates = rejected = 0
    host = db.merge(host)
    for sample in body.samples:
        age = (now - sample.ts).total_seconds()
        if age < -s.max_clock_skew_seconds or age > s.max_sample_age_seconds or len(sample.checks) > s.max_checks_per_sample:
            rejected += 1
            continue
        if db.get(models.Metric, (host.id, sample.ts)) is not None:
            duplicates += 1  # retry of an already-stored sample: idempotent
            continue
        db.add(models.Metric(host_id=host.id, ts=sample.ts, **sample.system.model_dump()))
        seen: set[str] = set()
        for c in sample.checks:
            if c.name in seen:
                continue
            seen.add(c.name)
            db.add(models.ServiceCheck(host_id=host.id, ts=sample.ts, **c.model_dump()))
        accepted += 1
    info = body.agent
    for field in ("hostname", "os", "os_version", "arch", "agent_version", "collection_interval"):
        v = getattr(info, field)
        if v is not None:
            setattr(host, field, v)
    # last_seen is advanced only by an authenticated, accepted ingest.
    if accepted or duplicates:
        host.last_seen = now
    db.commit()
    latest = s.latest_agent_version
    outdated = version_tuple(host.agent_version) < version_tuple(latest)
    return schemas.IngestResponse(accepted=accepted, duplicates=duplicates, rejected=rejected,
                                  latest_agent_version=latest, upgrade_available=outdated)


@router.get("/whoami")
def whoami(host: models.Host = Depends(authenticated_host)):
    """Lets an agent verify its credentials (used by `infrawatch-agent check`)."""
    return {"host_id": host.id, "hostname": host.hostname, "environment": host.environment}
