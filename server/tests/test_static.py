"""The SPA catch-all must never touch (or serve) files outside the frontend directory."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infrawatch_server.config import Settings
from infrawatch_server.main import create_app

SECRET = "TOP-SECRET-OUTSIDE-ROOT"


@pytest.fixture
def web(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>INDEX</html>")
    (root / "assets" / "app.js").write_text("console.log(1)")
    (root / "favicon.txt").write_text("FAVICON")
    outside = tmp_path / "secret.txt"
    outside.write_text(SECRET)
    (root / "leak").symlink_to(outside)  # symlink inside the root pointing outside it
    s = Settings(database_url="sqlite://", secret_key="k" * 40, admin_password="adminpassword1",
                 run_background_tasks=False, frontend_dir=str(root))
    with TestClient(create_app(s)) as c:
        yield c, root, outside


def test_serves_assets_root_files_and_spa_fallback(web):
    c, *_ = web
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/favicon.txt").text == "FAVICON"
    assert "INDEX" in c.get("/").text
    assert "INDEX" in c.get("/hosts/42").text  # client-side route
    assert c.get("/api/nope").status_code == 404


@pytest.mark.parametrize("path", [
    "../secret.txt", "..%2fsecret.txt", "%2e%2e/secret.txt", "%252e%252e%252fsecret.txt",
    "assets/../../secret.txt", "..\\secret.txt", "leak", "assets/%00../../secret.txt", "//etc/passwd", "/etc/passwd",
])
def test_traversal_and_symlink_never_leak(web, path):
    c, *_ = web
    r = c.get("/" + path)
    assert SECRET not in r.text
    assert r.status_code in (200, 400, 404)
    if r.status_code == 200:
        assert "INDEX" in r.text


def test_no_filesystem_probe_outside_root(web, monkeypatch):
    """Containment must be decided lexically/by resolved prefix BEFORE any is_file() stat on the candidate."""
    c, root, outside = web
    probed: list[Path] = []
    real = Path.is_file

    def spy(self, *a, **k):
        probed.append(self)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "is_file", spy)
    c.get("/../secret.txt")
    c.get("/..%2fsecret.txt")
    c.get("/leak")
    root_r = root.resolve()
    escaped = [p for p in probed if not p.resolve().is_relative_to(root_r)]
    assert escaped == []
