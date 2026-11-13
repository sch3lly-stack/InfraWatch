from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import Principal, audit, client_ip, current_user, get_db
from ..security import DUMMY_HASH, create_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
def login(body: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    s = request.app.state.settings
    request.app.state.limiter.check(f"login:{ip}", s.rate_limit_login_per_min)
    user = db.query(models.User).filter_by(username=body.username).one_or_none()
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not ok or user.disabled:
        audit(db, body.username[:64], "auth.login_failed", ip=ip)
        db.commit()
        raise HTTPException(401, "invalid username or password")
    audit(db, user.username, "auth.login", ip=ip)
    db.commit()
    return {"access_token": create_token(s.secret_key, user.username, user.role, s.token_ttl_minutes),
            "token_type": "bearer", "username": user.username, "role": user.role}


@router.get("/me")
def me(p: Principal = Depends(current_user)):
    return {"username": p.username, "role": p.role}
