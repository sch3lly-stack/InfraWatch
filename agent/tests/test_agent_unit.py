import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from infrawatch_agent.agent import Agent
from infrawatch_agent.buffer import SampleBuffer
from infrawatch_agent.checks import run_check
from infrawatch_agent.client import ServerClient
from infrawatch_agent.collector import SystemCollector
from infrawatch_agent.config import AgentConfig, CheckConfig, ConfigError, load_config, validate


def test_collector_returns_expected_fields():
    c = SystemCollector("/")
    c.collect()
    m = c.collect()
    for k in ("cpu_percent", "mem_percent", "mem_available_bytes", "disk_percent", "disk_free_bytes", "uptime_seconds",
              "net_sent_bps", "net_recv_bps", "load1"):
        assert k in m
    assert 0 <= m["cpu_percent"] <= 100 and 0 < m["mem_percent"] <= 100 and 0 < m["disk_percent"] <= 100
    assert m["uptime_seconds"] > 0 and m["net_sent_bps"] >= 0


def test_collector_bad_disk_path_degrades():
    m = SystemCollector("/definitely/not/here").collect()
    assert m["disk_percent"] is None and m["cpu_percent"] is not None


def test_config_validation(tmp_path):
    with pytest.raises(ConfigError):
        validate(AgentConfig(server_url="http://monitor.example.com"))  # plain http to remote host
    validate(AgentConfig(server_url="http://localhost:8000"))
    validate(AgentConfig(server_url="https://monitor.example.com"))
    with pytest.raises(ConfigError):
        validate(AgentConfig(server_url="https://x", interval=0))
    with pytest.raises(ConfigError):
        validate(AgentConfig(server_url="ftp://x"))
    with pytest.raises(ConfigError):
        validate(AgentConfig(server_url="https://x", checks=[CheckConfig("a", "tcp", "nohost")]))
    with pytest.raises(ConfigError):
        validate(AgentConfig(server_url="https://x", checks=[CheckConfig("a", "http", "x"), ]))
    p = tmp_path / "a.yaml"
    p.write_text("server_url: https://x\nbogus: 1\n")
    with pytest.raises(ConfigError, match="unknown"):
        load_config(p)
    p.write_text("server_url: https://x\ninterval: 30\nchecks:\n  - {name: web, kind: http, target: 'http://localhost/'}\n")
    cfg = load_config(p)
    assert cfg.interval == 30 and cfg.checks[0].name == "web"
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml")


def test_buffer_persists_and_bounds(tmp_path):
    p = tmp_path / "b.db"
    b = SampleBuffer(p, 10)
    for i in range(15):
        b.add({"i": i})
    assert len(b) == 10 and b.dropped == 5
    assert b.peek(1)[0][1] == {"i": 5}  # oldest were dropped
    b.close()
    b2 = SampleBuffer(p, 10)  # survives restart
    assert len(b2) == 10
    ids = [i for i, _ in b2.peek(3)]
    b2.delete(ids)
    assert len(b2) == 7
    assert oct(p.stat().st_mode & 0o777) == "0o600"


class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        code = 500 if self.path == "/fail" else 200
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def test_checks():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    r = run_check(CheckConfig("ok", "http", f"http://127.0.0.1:{port}/"))
    assert r["ok"] and r["status_code"] == 200 and r["response_ms"] >= 0
    r = run_check(CheckConfig("bad", "http", f"http://127.0.0.1:{port}/fail"))
    assert not r["ok"] and r["status_code"] == 500 and r["error"] == "HTTP 500"
    assert run_check(CheckConfig("tcp", "tcp", f"127.0.0.1:{port}"))["ok"]
    s = socket.socket(); s.bind(("127.0.0.1", 0)); closed = s.getsockname()[1]; s.close()
    r = run_check(CheckConfig("closed", "tcp", f"127.0.0.1:{closed}"))
    assert not r["ok"]
    r = run_check(CheckConfig("down", "http", f"http://127.0.0.1:{closed}/", timeout=1))
    assert not r["ok"] and r["error"]
    assert run_check(CheckConfig("py", "process", "python"))["ok"] in (True, False)
    assert not run_check(CheckConfig("none", "process", "no-such-process-xyz"))["ok"]
    srv.shutdown()


def make_agent(tmp_path, handler, **kw):
    cfg = AgentConfig(server_url="http://localhost:9", state_dir=tmp_path, interval=1, api_key="iw_1_secret", **kw)
    client = ServerClient(cfg, transport=httpx.MockTransport(handler))
    waits = []
    a = Agent(cfg, client, sleep=lambda d: waits.append(d) or False)
    a.api_key = cfg.api_key
    return a, waits


def test_agent_buffers_when_server_down_then_drains(tmp_path):
    state = {"up": False, "got": []}

    def handler(req):
        if not state["up"]:
            raise httpx.ConnectError("down")
        body = json.loads(req.content)
        state["got"] += body["samples"]
        return httpx.Response(200, json={"accepted": len(body["samples"]), "duplicates": 0, "rejected": 0,
                                         "latest_agent_version": "0.1.0", "upgrade_available": False})

    a, waits = make_agent(tmp_path, handler)
    for _ in range(3):
        a.collect_once()
        assert a.flush() is False
    assert len(a.buffer) == 3 and a.consecutive_failures == 3
    assert a.backoff_delay() > 1  # exponential backoff engaged
    state["up"] = True
    a.collect_once()
    assert a.flush() is True
    assert len(a.buffer) == 0 and len(state["got"]) == 4 and a.consecutive_failures == 0
    ts = [s["ts"] for s in state["got"]]
    assert ts == sorted(ts)  # delivered in order


def test_poison_batch_is_dropped_not_stuck(tmp_path):
    def handler(req):
        return httpx.Response(422, json={"detail": "bad"})

    a, _ = make_agent(tmp_path, handler)
    a.collect_once()
    assert a.flush() is True and len(a.buffer) == 0


def test_server_5xx_and_429_are_retried(tmp_path):
    codes = iter([500, 429, 200])

    def handler(req):
        c = next(codes)
        return httpx.Response(c, json={"accepted": 1})

    a, _ = make_agent(tmp_path, handler)
    a.collect_once()
    assert not a.flush() and not a.flush() and len(a.buffer) == 1
    assert a.flush() and len(a.buffer) == 0


def test_graceful_shutdown_flushes_and_writes_health(tmp_path):
    sent = []

    def handler(req):
        sent.append(json.loads(req.content)["samples"])
        return httpx.Response(200, json={"accepted": 1})

    a, _ = make_agent(tmp_path, handler)
    a.run(max_iterations=2)
    assert sum(len(s) for s in sent) == 2
    h = json.loads((tmp_path / "health.json").read_text())
    assert h["buffered_samples"] == 0 and h["sent_total"] == 2


def test_agent_payload_contains_only_resource_metrics(tmp_path):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"accepted": 1})

    a, _ = make_agent(tmp_path, handler)
    a.collect_once(); a.flush()
    assert set(seen["body"]) == {"agent", "samples"}
    assert set(seen["body"]["agent"]) <= {"hostname", "os", "os_version", "arch", "agent_version", "collection_interval"}
    assert set(seen["body"]["samples"][0]) == {"ts", "system", "checks"}
