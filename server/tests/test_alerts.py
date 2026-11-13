from datetime import datetime, timedelta, timezone

from conftest import push, register_host, sample
from infrawatch_server import models
from infrawatch_server.alerts import evaluate


def rule(client, admin, **kw):
    body = {"name": "r", "type": "cpu_high", "threshold": 80, "severity": "critical", "cooldown_seconds": 300, **kw}
    r = client.post("/api/v1/rules", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def run(app, now=None):
    with app.state.db.session() as s:
        return evaluate(s, app.state.settings, app.state.notifier, now or datetime.now(timezone.utc))


def alerts(client, admin, status="active"):
    return client.get(f"/api/v1/alerts?status={status}", headers=admin).json()


def test_threshold_alert_opens_and_notifies(client, admin, app):
    hid, key = register_host(client, admin)
    client.post("/api/v1/channels", json={"name": "hook", "url": "http://localhost:9/h"}, headers=admin)
    rule(client, admin)
    push(client, key, sample(cpu=95))
    assert run(app)["opened"] == 1
    a = alerts(client, admin)
    assert len(a) == 1 and a[0]["severity"] == "critical" and a[0]["value"] == 95
    assert [e for _, e, _ in app.state.notifier.sent] == ["alert.opened"]


def test_no_alert_below_threshold(client, admin, app):
    _, key = register_host(client, admin)
    rule(client, admin)
    push(client, key, sample(cpu=50))
    assert run(app)["opened"] == 0 and alerts(client, admin) == []


def test_duplicate_suppression_no_storm(client, admin, app):
    _, key = register_host(client, admin)
    client.post("/api/v1/channels", json={"name": "hook", "url": "http://localhost:9/h"}, headers=admin)
    rule(client, admin)
    push(client, key, sample(cpu=95))
    for _ in range(20):
        run(app)
    a = alerts(client, admin)
    assert len(a) == 1 and a[0]["occurrences"] == 20
    assert len(app.state.notifier.sent) == 1  # one notification, not 20


def test_auto_resolve_and_cooldown(client, admin, app):
    _, key = register_host(client, admin)
    rule(client, admin, cooldown_seconds=600)
    now = datetime.now(timezone.utc) - timedelta(hours=2)  # simulated clock in the past (server rejects future samples)
    push(client, key, sample(ts=now, cpu=95))
    run(app, now)
    push(client, key, sample(ts=now + timedelta(seconds=15), cpu=20))
    assert run(app, now + timedelta(seconds=16))["resolved"] == 1
    assert alerts(client, admin) == [] and len(alerts(client, admin, "resolved")) == 1
    # flap back within cooldown -> suppressed
    push(client, key, sample(ts=now + timedelta(seconds=30), cpu=99))
    st = run(app, now + timedelta(seconds=31))
    assert st["opened"] == 0 and st["cooldown"] == 1
    # after the cooldown it opens again
    push(client, key, sample(ts=now + timedelta(seconds=700), cpu=99))
    assert run(app, now + timedelta(seconds=701))["opened"] == 1
    assert len(alerts(client, admin, "resolved")) == 1 and len(alerts(client, admin)) == 1


def test_ack_and_resolve_workflow(client, admin, app):
    from conftest import make_user
    viewer = make_user(client, admin, "viewer")
    op = make_user(client, admin, "operator")
    _, key = register_host(client, admin)
    rule(client, admin)
    push(client, key, sample(cpu=95))
    run(app)
    aid = alerts(client, admin)[0]["id"]
    assert client.post(f"/api/v1/alerts/{aid}/acknowledge", headers=viewer).status_code == 403
    r = client.post(f"/api/v1/alerts/{aid}/acknowledge", headers=op).json()
    assert r["status"] == "acknowledged" and r["acknowledged_by"] == "user_operator"
    assert client.post(f"/api/v1/alerts/{aid}/acknowledge", headers=op).status_code == 409
    run(app)  # ack'd alert is still deduplicated
    assert len(alerts(client, admin, "all" if False else "active")) == 1
    r = client.post(f"/api/v1/alerts/{aid}/resolve", headers=op).json()
    assert r["status"] == "resolved" and r["resolved_by"] == "user_operator"
    assert client.post(f"/api/v1/alerts/{aid}/resolve", headers=op).status_code == 409
    # manually resolved while condition persists: cooldown prevents immediate re-open
    assert run(app)["opened"] == 0


def test_sustained_condition_required(client, admin, app):
    _, key = register_host(client, admin)
    rule(client, admin, for_seconds=120)
    now = datetime.now(timezone.utc)
    push(client, key, sample(ts=now, cpu=95))
    assert run(app, now)["opened"] == 0  # a single spike is not enough
    samples = [sample(ts=now - timedelta(seconds=s), cpu=95) for s in range(0, 200, 15)]
    push(client, key, *samples)
    assert run(app, now)["opened"] == 1


def test_host_down_alert(client, admin, app):
    hid, key = register_host(client, admin)
    rule(client, admin, type="host_down", threshold=None, name="down")
    now = datetime.now(timezone.utc)
    push(client, key, sample(ts=now))
    assert run(app, now)["opened"] == 0
    assert run(app, now + timedelta(seconds=30))["opened"] == 0
    assert run(app, now + timedelta(seconds=300))["opened"] == 1
    assert client.get(f"/api/v1/hosts/{hid}", headers=admin).json()["status"] in ("online", "offline")
    # reconnect -> resolves
    push(client, key, sample(ts=datetime.now(timezone.utc)))
    assert run(app, datetime.now(timezone.utc))["resolved"] == 1


def test_never_reported_host_not_alerted(client, admin, app):
    register_host(client, admin)
    rule(client, admin, type="host_down", threshold=None, name="down")
    assert run(app, datetime.now(timezone.utc) + timedelta(days=1))["opened"] == 0


def test_service_down_and_slow_response(client, admin, app):
    _, key = register_host(client, admin)
    rule(client, admin, type="service_down", threshold=None, name="svc")
    rule(client, admin, type="response_slow", threshold=500, severity="warning", name="slow")
    base = {"kind": "http", "target": "http://x"}
    push(client, key, sample(checks=[{**base, "name": "api", "ok": False, "error": "timeout"},
                                      {**base, "name": "web", "ok": True, "response_ms": 900.0}]))
    run(app)
    titles = sorted(a["title"] for a in alerts(client, admin))
    assert len(titles) == 2 and any("api" in t for t in titles) and any("web" in t for t in titles)


def test_disk_low_uses_free_space(client, admin, app):
    _, key = register_host(client, admin)
    rule(client, admin, type="disk_low", threshold=10, name="disk")
    push(client, key, sample(disk=95))  # 5% free < 10%
    assert run(app)["opened"] == 1


def test_maintenance_window_suppresses(client, admin, app):
    hid, key = register_host(client, admin)
    rule(client, admin)
    now = datetime.now(timezone.utc) - timedelta(hours=3)
    r = client.post("/api/v1/maintenance", json={"name": "patching", "host_id": hid,
                    "starts_at": (now - timedelta(minutes=5)).isoformat(), "ends_at": (now + timedelta(hours=1)).isoformat()},
                    headers=admin)
    assert r.status_code == 201
    push(client, key, sample(ts=now, cpu=99))
    st = run(app, now)
    assert st["opened"] == 0 and st["maintenance"] == 1
    # after the window ends, alert fires
    assert run(app, now + timedelta(hours=2))["opened"] == 0  # data is stale by then, nothing to alert on
    push(client, key, sample(ts=now + timedelta(hours=2), cpu=99))  # still ~1h in the past
    assert run(app, now + timedelta(hours=2))["opened"] == 1


def test_rule_scoping_by_environment(client, admin, app):
    _, k1 = register_host(client, admin, "p", "production")
    _, k2 = register_host(client, admin, "s", "staging")
    rule(client, admin, environment="production")
    push(client, k1, sample(cpu=99))
    push(client, k2, sample(cpu=99))
    run(app)
    a = alerts(client, admin)
    assert len(a) == 1 and a[0]["hostname"] == "p"


def test_disabling_rule_resolves_alert(client, admin, app):
    _, key = register_host(client, admin)
    r = rule(client, admin)
    push(client, key, sample(cpu=99))
    run(app)
    body = {k: r[k] for k in ("name", "type", "threshold", "for_seconds", "severity", "cooldown_seconds", "host_id", "environment", "group", "service_name")}
    client.put(f"/api/v1/rules/{r['id']}", json={**body, "enabled": False}, headers=admin)
    run(app)
    assert alerts(client, admin) == []


def test_failed_notification_does_not_break_evaluation(client, admin, app):
    from infrawatch_server.notify import Notifier
    app.state.settings.webhook_timeout_seconds = 0.5
    _, key = register_host(client, admin)
    client.post("/api/v1/channels", json={"name": "dead", "url": "http://127.0.0.1:9/h"}, headers=admin)
    rule(client, admin)
    push(client, key, sample(cpu=99))
    app.state.notifier = Notifier(app.state.settings)  # real notifier -> connection refused
    assert run(app)["opened"] == 1


def test_report_summary(client, admin):
    _, key = register_host(client, admin)
    push(client, key, sample(cpu=40), sample(ts=datetime.now(timezone.utc) - timedelta(seconds=15), cpu=60))
    rep = client.get("/api/v1/reports/summary?range=24h", headers=admin).json()
    assert rep["hosts"][0]["avg_cpu"] == 50.0 and rep["hosts"][0]["max_cpu"] == 60.0
