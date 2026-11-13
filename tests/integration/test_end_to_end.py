"""Real agent <-> real server (uvicorn) over real sockets."""
import threading
import time

import httpx
import pytest

from infrawatch_agent.agent import Agent, register
from infrawatch_agent.client import ServerClient
from infrawatch_agent.config import AgentConfig, CheckConfig, ConfigError, validate


def agent_cfg(live, tmp_path, token=None, **kw):
    return AgentConfig(server_url=live.url, state_dir=tmp_path / "agent", interval=1,
                       enrollment_token=token or live.enrollment_token(), ca_bundle=str(live.ca) if live.ca else None,
                       http_timeout=3, **kw)


def hosts(live, **params):
    with live.http() as c:
        return c.get("/api/v1/hosts", params=params, headers=live.admin_headers()).json()


def test_register_and_report_makes_host_online(live, tmp_path):
    cfg = agent_cfg(live, tmp_path, checks=[CheckConfig("self", "http", f"{live.url}/api/v1/health")])
    agent = Agent(cfg)
    assert hosts(live) == []
    agent.run(max_iterations=3)
    h = hosts(live)
    assert len(h) == 1 and h[0]["status"] == "online" and h[0]["latest"]["cpu_percent"] is not None
    assert h[0]["agent_version"] == "0.1.0" and h[0]["os"]
    with live.http() as c:
        svc = c.get(f"/api/v1/hosts/{h[0]['id']}/services", headers=live.admin_headers()).json()
    assert svc[0]["name"] == "self" and svc[0]["ok"]
    assert (tmp_path / "agent" / "agent.key").stat().st_mode & 0o777 == 0o600


def test_https_with_custom_ca(live_tls, tmp_path):
    Agent(agent_cfg(live_tls, tmp_path)).run(max_iterations=2)
    assert hosts(live_tls)[0]["status"] == "online"


def test_https_rejects_untrusted_certificate(live_tls, tmp_path):
    cfg = AgentConfig(server_url=live_tls.url, state_dir=tmp_path / "a", enrollment_token="x", http_timeout=3)  # no CA
    agent = Agent(cfg)
    agent.run(max_iterations=1)
    assert agent.api_key is None and hosts(live_tls) == []  # TLS verification failed -> nothing sent


def test_outage_buffering_and_reconnect(tmp_path):
    from conftest import LiveServer
    live = LiveServer(tmp_path)
    live.start()
    cfg = agent_cfg(live, tmp_path)
    agent = Agent(cfg, sleep=lambda d: False)  # no real sleeping between iterations
    agent.run(max_iterations=2)
    # keep server DB, then take the server down
    live.stop()
    agent2 = Agent(cfg, sleep=lambda d: False)
    agent2.api_key = (tmp_path / "agent" / "agent.key").read_text().strip()
    for _ in range(4):
        agent2.collect_once()
        assert agent2.flush() is False
    assert len(agent2.buffer) == 4 and agent2.consecutive_failures >= 1
    live2 = LiveServer(tmp_path, port=live.port)  # same DB file, same port
    live2.start()
    try:
        agent2.collect_once()
        assert agent2.flush() is True
        assert len(agent2.buffer) == 0
        h = hosts(live2)[0]
        with live2.http() as c:
            pts = c.get(f"/api/v1/hosts/{h['id']}/metrics/export?format=json&range=1h",
                        headers=live2.admin_headers()).json()  # raw rows (the chart endpoint averages buckets)
        assert len(pts) >= 6  # 2 before the outage + 4 buffered + 1
    finally:
        live2.stop()


def test_revoked_agent_is_rejected(live, tmp_path):
    cfg = agent_cfg(live, tmp_path)
    agent = Agent(cfg)
    agent.run(max_iterations=1)
    hid = hosts(live)[0]["id"]
    with live.http() as c:
        c.patch(f"/api/v1/hosts/{hid}", json={"revoked": True}, headers=live.admin_headers())
    agent = Agent(cfg, sleep=lambda d: False)
    agent.api_key = (tmp_path / "agent" / "agent.key").read_text().strip()
    agent.collect_once()
    from infrawatch_agent.client import AuthError
    with pytest.raises(AuthError):
        agent.flush()
    assert len(agent.buffer) == 1  # data kept, never lost on auth failure


def test_two_agents_one_server_are_isolated(live, tmp_path):
    a = Agent(agent_cfg(live, tmp_path / "a", token=live.enrollment_token("prod")))
    b = Agent(agent_cfg(live, tmp_path / "b", token=live.enrollment_token("staging")))
    a.run(max_iterations=1); b.run(max_iterations=1)
    h = hosts(live)
    assert len(h) == 2 and {x["environment"] for x in h} == {"prod", "staging"} and all(x["status"] == "online" for x in h)


def test_alert_fires_end_to_end(live, tmp_path):
    from infrawatch_server.alerts import evaluate
    from infrawatch_server.models import utcnow
    with live.http() as c:
        r = c.post("/api/v1/rules", json={"name": "cpu0", "type": "mem_high", "threshold": 0.1, "severity": "critical"},
                   headers=live.admin_headers())
        assert r.status_code == 201
    Agent(agent_cfg(live, tmp_path)).run(max_iterations=1)
    with live.app.state.db.session() as s:
        assert evaluate(s, live.settings, live.app.state.notifier, utcnow())["opened"] == 1
    with live.http() as c:
        a = c.get("/api/v1/alerts?status=active", headers=live.admin_headers()).json()
    assert len(a) == 1 and a[0]["severity"] == "critical"
