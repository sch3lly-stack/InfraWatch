from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete

from . import __version__, models
from .alerts import evaluate
from .config import Settings, get_settings
from .db import Database
from .models import utcnow
from .notify import Notifier
from .ratelimit import RateLimiter
from .routers import admin, agents, alerts_api, auth, hosts
from .security import hash_password, new_secret

log = logging.getLogger("infrawatch")


def bootstrap_admin(db: Database, settings: Settings) -> None:
    with db.session() as s:
        if s.query(models.User).count():
            return
        pw = settings.admin_password
        generated = not pw
        pw = pw or new_secret(12)
        s.add(models.User(username=settings.admin_username, password_hash=hash_password(pw), role="admin"))
        s.commit()
    if generated:
        # Printed once so the operator can log in; set INFRAWATCH_ADMIN_PASSWORD to avoid this.
        log.warning("Created initial admin '%s' with generated password: %s", settings.admin_username, pw)


def run_cycle(app: FastAPI) -> dict:
    """One evaluation + retention pass. Synchronous; called from a worker thread."""
    s: Settings = app.state.settings
    now = utcnow()
    with app.state.db.session() as session:
        stats = evaluate(session, s, app.state.notifier, now)
        cutoff = now - timedelta(days=s.metric_retention_days)
        session.execute(delete(models.Metric).where(models.Metric.ts < cutoff))
        session.execute(delete(models.ServiceCheck).where(models.ServiceCheck.ts < cutoff))
        session.commit()
    return stats


async def _loop(app: FastAPI) -> None:
    interval = app.state.settings.evaluation_interval_seconds
    while True:
        try:
            await asyncio.to_thread(run_cycle, app)
        except Exception:
            log.exception("evaluation cycle failed")
        await asyncio.sleep(interval)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        db.create_all()
        bootstrap_admin(db, settings)
        task = asyncio.create_task(_loop(app)) if settings.run_background_tasks else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="InfraWatch", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings, app.state.db = settings, db
    app.state.limiter, app.state.notifier = RateLimiter(), Notifier(settings)

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                           allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        if not request.url.path.startswith("/api/docs"):
            resp.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    for r in (auth.router, agents.router, hosts.router, alerts_api.router, admin.router):
        app.include_router(r)

    @app.get("/api/v1/health", tags=["meta"])
    def health():
        return {"status": "ok", "version": __version__}

    fdir = Path(settings.frontend_dir)
    if fdir.is_dir():
        app.mount("/assets", StaticFiles(directory=fdir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            f = (fdir / path).resolve()
            if path and f.is_file() and fdir.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(fdir / "index.html")

    return app


def app_factory() -> FastAPI:  # uvicorn --factory infrawatch_server.main:app_factory
    logging.basicConfig(level=os.getenv("INFRAWATCH_LOG_LEVEL", "INFO"),
                        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    return create_app()
