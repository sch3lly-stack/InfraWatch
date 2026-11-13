import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from infrawatch_server.config import Settings
from infrawatch_server.main import create_app


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class LiveServer:
    def __init__(self, tmp_path: Path, tls: bool = False, port: int | None = None):
        self.port = port or free_port()
        self.tls = tls
        self.settings = Settings(database_url=f"sqlite:///{tmp_path}/server.db", secret_key="k" * 40,
                                 admin_password="adminpassword1", run_background_tasks=False,
                                 frontend_dir="/nonexistent", allow_private_webhooks=True)
        self.app = create_app(self.settings)
        kwargs = {}
        self.ca = None
        if tls:
            self.ca = tmp_path / "cert.pem"
            key = tmp_path / "key.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
                            "-out", str(self.ca), "-days", "1", "-subj", "/CN=localhost",
                            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
            kwargs = {"ssl_keyfile": str(key), "ssl_certfile": str(self.ca)}
        self.config = uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning", **kwargs)
        self.server = uvicorn.Server(self.config)
        self.thread: threading.Thread | None = None

    @property
    def url(self):
        return f"{'https' if self.tls else 'http'}://localhost:{self.port}"

    def start(self):
        self.server.should_exit = False
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return
            time.sleep(0.1)
        raise RuntimeError("server did not start")

    def stop(self):
        self.server.should_exit = True
        if self.thread:
            self.thread.join(10)

    def http(self):
        import ssl
        return httpx.Client(base_url=self.url, verify=ssl.create_default_context(cafile=str(self.ca)) if self.ca else True)

    def admin_headers(self):
        with self.http() as c:
            t = c.post("/api/v1/auth/login", json={"username": "admin", "password": "adminpassword1"}).json()["access_token"]
        return {"Authorization": f"Bearer {t}"}

    def enrollment_token(self, environment="production"):
        with self.http() as c:
            return c.post("/api/v1/enrollment-tokens", json={"environment": environment},
                          headers=self.admin_headers()).json()["token"]


@pytest.fixture
def live(tmp_path):
    s = LiveServer(tmp_path)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def live_tls(tmp_path):
    s = LiveServer(tmp_path, tls=True)
    s.start()
    yield s
    s.stop()
