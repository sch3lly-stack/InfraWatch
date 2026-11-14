"""First-run admin password is never logged; it is written once to a 0600 file."""
import logging
import os
import stat

import pytest
from fastapi.testclient import TestClient
from infrawatch_server import models
from infrawatch_server.config import Settings
from infrawatch_server.db import Database
from infrawatch_server.main import bootstrap_admin, create_app


def _settings(password_file, **overrides):
    values = {
        "database_url": "sqlite://",
        "secret_key": "test-secret-key-0123456789-0123456789",
        "admin_username": "admin",
        "admin_password": "",
        "initial_password_file": str(password_file),
        "run_background_tasks": False,
        "frontend_dir": "/nonexistent",
    }
    values.update(overrides)
    return Settings(**values)


def _logged(caplog) -> str:
    parts = []
    for record in caplog.records:
        parts.append(record.getMessage())
        if record.args:
            parts.append(repr(record.args))
    return "\n".join(parts)


def test_generated_password_is_not_logged_and_file_is_0600(tmp_path, caplog):
    path = tmp_path / "initial-admin-password.txt"
    app = create_app(_settings(path))
    with caplog.at_level(logging.DEBUG, logger="infrawatch"), TestClient(app) as client:
        assert path.is_file()
        password = path.read_text(encoding="utf-8").strip()
        assert password
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        logged = _logged(caplog)
        assert password not in logged
        assert str(path) in logged
        assert "delete" in logged.lower()
        response = client.post("/api/v1/auth/login", json={"username": "admin", "password": password})
        assert response.status_code == 200, response.text


def test_existing_password_file_is_not_overwritten(tmp_path, caplog):
    path = tmp_path / "initial-admin-password.txt"
    original = "already-set-password\n"
    path.write_text(original, encoding="utf-8")
    os.chmod(path, 0o640)
    settings = _settings(path)
    db = Database(settings.database_url)
    db.create_all()
    with caplog.at_level(logging.DEBUG, logger="infrawatch"), pytest.raises(FileExistsError):
        bootstrap_admin(db, settings)
    assert path.read_text(encoding="utf-8") == original
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert "already-set-password" not in _logged(caplog)
    with db.session() as session:
        assert session.query(models.User).count() == 0


def test_second_start_does_not_rewrite_password_file(tmp_path, caplog):
    path = tmp_path / "initial-admin-password.txt"
    settings = _settings(path)
    db = Database(settings.database_url)
    db.create_all()
    bootstrap_admin(db, settings)
    password = path.read_text(encoding="utf-8").strip()
    mode = stat.S_IMODE(path.stat().st_mode)
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="infrawatch"):
        bootstrap_admin(db, settings)
    assert path.read_text(encoding="utf-8").strip() == password
    assert stat.S_IMODE(path.stat().st_mode) == mode
    assert password not in _logged(caplog)


def test_configured_password_is_not_logged_or_written(tmp_path, caplog):
    path = tmp_path / "initial-admin-password.txt"
    app = create_app(_settings(path, admin_password="adminpassword1"))
    with caplog.at_level(logging.DEBUG, logger="infrawatch"), TestClient(app) as client:
        assert not path.exists()
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "adminpassword1"},
        )
        assert response.status_code == 200, response.text
        assert "adminpassword1" not in _logged(caplog)
