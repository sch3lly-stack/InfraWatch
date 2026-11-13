from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .config import Settings
from .security import ROLE_RANK, constant_time_eq, decode_token, parse_agent_key, sha256_hex


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.db.session()
    try:
        yield session
    finally:
        session.close()


def client_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip() or None
    return None


class Principal:
    def __init__(self, username: str, role: str):
        self.username, self.role = username, role


def current_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    request.app.state.limiter.check(f"api:{client_ip(request)}", request.app.state.settings.rate_limit_api_per_min)
    token = _bearer(request)
    claims = decode_token(request.app.state.settings.secret_key, token) if token else None
    if not claims:
        raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
    user = db.query(models.User).filter_by(username=claims["sub"]).one_or_none()
    # Re-read role from DB so demotion/disable takes effect immediately.
    if not user or user.disabled:
        raise HTTPException(401, "not authenticated")
    return Principal(user.username, user.role)


def require_role(minimum: str):
    def dep(p: Principal = Depends(current_user)) -> Principal:
        if ROLE_RANK[p.role] < ROLE_RANK[minimum]:
            raise HTTPException(403, f"requires role '{minimum}'")
        return p

    return dep


def authenticated_host(request: Request, db: Session = Depends(get_db)) -> models.Host:
    """Resolve the calling agent from its API key. Identity comes ONLY from the key,
    never from request payload, so an agent cannot report as another host."""
    key = _bearer(request)
    parsed = parse_agent_key(key) if key else None
    if not parsed:
        raise HTTPException(401, "invalid agent credentials")
    host_id, secret = parsed
    request.app.state.limiter.check(f"ingest:{host_id}", request.app.state.settings.rate_limit_ingest_per_min)
    host = db.get(models.Host, host_id)
    ok = host is not None and constant_time_eq(host.api_key_hash, sha256_hex(secret))
    if not ok or host.revoked:
        raise HTTPException(401, "invalid agent credentials")
    return host


def audit(db: Session, actor: str, action: str, target: str = "", ip: str = "", **detail) -> None:
    db.add(models.AuditLog(actor=actor, action=action, target=target, ip=ip, detail=detail))
