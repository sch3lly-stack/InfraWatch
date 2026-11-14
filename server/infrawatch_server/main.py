from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import timedelta
from pathlib import Path, PurePosixPath

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


def _write_initial_password(path: Path, password: str) -> None:
    """Create `path` exclusively, mode 0600, containing `password` and a trailing newline.

    An existing file is left untouched. FileExistsError propagates so startup fails closed
    instead of creating an admin whose password was not saved.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        log.error(
            "Initial admin password file %s already exists and was not overwritten. "
            "Delete that file or set INFRAWATCH_ADMIN_PASSWORD.",
            path,
        )
        raise
    try:
        os.fchmod(fd, 0o600)
        payload = (password + "\n").encode("utf-8")
        if os.write(fd, payload) != len(payload):
            raise OSError(f"short write creating {path}")
    except Exception:
        os.close(fd)
        with contextlib.suppress(OSError):
            path.unlink()
        raise
    os.close(fd)


def bootstrap_admin(db: Database, settings: Settings) -> None:
    with db.session() as s:
        if s.query(models.User).count():
            return
        pw = settings.admin_password
        generated = not pw
        if generated:
            pw = new_secret(12)
            _write_initial_password(Path(settings.initial_password_file), pw)
        s.add(models.User(username=settings.admin_username, password_hash=hash_password(pw), role="admin"))
        s.commit()
    if generated:
        log.warning(
            "Generated admin password written to %s; read it, then delete that file.",
            settings.initial_password_file,
        )


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
        root = os.path.realpath(fdir)
        app.mount("/assets", StaticFiles(directory=os.path.join(root, "assets")), name="assets")

        def _safe_static_file(path: str) -> str | None:
            """Return an absolute file path inside the frontend root for `path`, or None.

            Validation happens before any stat on user input: reject NUL bytes, backslashes, absolute paths and `..`
            segments lexically, then `realpath` (which follows symlinks) and require the result to stay under the
            root (`startswith(root + os.sep)`) before the filesystem is probed.
            """
            if not path or "\x00" in path or "\\" in path or path.startswith("/") or ".." in PurePosixPath(path).parts:
                return None
            full = os.path.realpath(os.path.join(root, path))
            if not full.startswith(root + os.sep):
                return None
            return full if os.path.isfile(full) else None

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            return FileResponse(_safe_static_file(path) or os.path.join(root, "index.html"))

    return app


def app_factory() -> FastAPI:  # uvicorn --factory infrawatch_server.main:app_factory
    logging.basicConfig(level=os.getenv("INFRAWATCH_LOG_LEVEL", "INFO"),
                        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    return create_app()
