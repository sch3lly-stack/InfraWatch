import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from infrawatch_server.config import Settings
from infrawatch_server.main import create_app


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, channel, event, alert):
        self.sent.append((channel.name, event, alert.id))
        return True


@pytest.fixture
def app():
    # CI sets INFRAWATCH_TEST_DATABASE_URL to run the same suite against PostgreSQL/TimescaleDB.
    s = Settings(database_url=os.environ.get("INFRAWATCH_TEST_DATABASE_URL", "sqlite://"), secret_key="test-secret-key-0123456789-0123456789",
                 admin_password="adminpassword1", run_background_tasks=False, frontend_dir="/nonexistent",
                 allow_private_webhooks=True)
    app = create_app(s)
    app.state.notifier = FakeNotifier()
    if s.database_url != "sqlite://":  # start every test from an empty schema on a real server DB
        from infrawatch_server.db import Base
        from infrawatch_server import models  # noqa: F401
        Base.metadata.drop_all(app.state.db.engine)
    yield app
    if s.database_url != "sqlite://":
        app.state.db.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def login(client, username="admin", password="adminpassword1"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return login(client)


def make_user(client, admin, role, name=None):
    name = name or f"user_{role}"
    r = client.post("/api/v1/users", json={"username": name, "password": "longenoughpw1", "role": role}, headers=admin)
    assert r.status_code == 201, r.text
    return login(client, name, "longenoughpw1")


def register_host(client, admin, hostname="web-1", environment="production"):
    t = client.post("/api/v1/enrollment-tokens", json={"environment": environment, "group": "web"}, headers=admin).json()
    r = client.post("/api/v1/agents/register", json={"hostname": hostname, "os": "Linux", "agent_version": "0.1.0"},
                    headers={"Authorization": f"Bearer {t['token']}"})
    assert r.status_code == 201, r.text
    d = r.json()
    return d["host_id"], {"Authorization": f"Bearer {d['api_key']}"}


def sample(ts=None, cpu=10.0, mem=40.0, disk=50.0, checks=None):
    ts = ts or datetime.now(timezone.utc)
    return {"ts": ts.isoformat(), "system": {"cpu_percent": cpu, "mem_percent": mem, "disk_percent": disk,
                                             "net_sent_bps": 1.0, "net_recv_bps": 2.0, "uptime_seconds": 100},
            "checks": checks or []}


def push(client, key, *samples, agent=None):
    return client.post("/api/v1/agents/metrics", json={"agent": agent or {}, "samples": list(samples)}, headers=key)
