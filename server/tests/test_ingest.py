from datetime import datetime, timedelta, timezone

from conftest import push, register_host, sample


def test_registered_host_is_pending_until_first_report(client, admin):
    hid, key = register_host(client, admin)
    h = client.get(f"/api/v1/hosts/{hid}", headers=admin).json()
    assert h["status"] == "pending" and h["last_seen"] is None
    ov = client.get("/api/v1/overview", headers=admin).json()
    assert ov["total"] == 1 and ov["online"] == 0 and ov["pending"] == 0 + 1
    assert push(client, key, sample()).status_code == 200
    h = client.get(f"/api/v1/hosts/{hid}", headers=admin).json()
    assert h["status"] == "online" and h["last_seen"]


def test_ingest_persists_and_queries(client, admin):
    hid, key = register_host(client, admin)
    now = datetime.now(timezone.utc)
    samples = [sample(ts=now - timedelta(seconds=15 * i), cpu=10 + i) for i in range(10)]
    r = push(client, key, *samples, agent={"agent_version": "0.1.0", "os_version": "14.2"})
    assert r.json()["accepted"] == 10
    m = client.get(f"/api/v1/hosts/{hid}/metrics?range=1h&max_points=300", headers=admin).json()
    assert len(m["points"]) == 10
    assert client.get(f"/api/v1/hosts/{hid}", headers=admin).json()["os_version"] == "14.2"


def test_duplicate_resend_is_idempotent(client, admin):
    hid, key = register_host(client, admin)
    s = sample()
    assert push(client, key, s).json()["accepted"] == 1
    r = push(client, key, s).json()
    assert r["accepted"] == 0 and r["duplicates"] == 1
    assert len(client.get(f"/api/v1/hosts/{hid}/metrics", headers=admin).json()["points"]) == 1


def test_future_and_ancient_samples_rejected(client, admin):
    _, key = register_host(client, admin)
    now = datetime.now(timezone.utc)
    r = push(client, key, sample(ts=now + timedelta(hours=1)), sample(ts=now - timedelta(days=30))).json()
    assert r["rejected"] == 2 and r["accepted"] == 0


def test_batch_limit(client, admin, app):
    _, key = register_host(client, admin)
    app.state.settings.max_batch_samples = 3
    now = datetime.now(timezone.utc)
    r = push(client, key, *[sample(ts=now - timedelta(seconds=i)) for i in range(4)])
    assert r.status_code == 413


def test_ingest_rate_limited(client, admin, app):
    _, key = register_host(client, admin)
    app.state.settings.rate_limit_ingest_per_min = 3
    codes = [push(client, key, sample(ts=datetime.now(timezone.utc) - timedelta(seconds=i))).status_code for i in range(5)]
    assert codes[:3] == [200] * 3 and 429 in codes


def test_service_checks_and_availability(client, admin):
    hid, key = register_host(client, admin)
    now = datetime.now(timezone.utc)
    ok = {"name": "api", "kind": "http", "target": "http://x/health", "ok": True, "response_ms": 12.5, "status_code": 200}
    bad = {**ok, "ok": False, "status_code": 503, "response_ms": None, "error": "HTTP 503"}
    push(client, key, sample(ts=now - timedelta(seconds=30), checks=[ok]), sample(ts=now - timedelta(seconds=15), checks=[ok]),
         sample(ts=now, checks=[bad]))
    svc = client.get(f"/api/v1/hosts/{hid}/services", headers=admin).json()
    assert len(svc) == 1 and svc[0]["ok"] is False and svc[0]["failed_checks"] == 1
    assert svc[0]["availability_percent"] == 66.67


def test_simulated_data_is_separated(client, admin, app):
    from infrawatch_server import models
    from infrawatch_server.models import utcnow
    register_host(client, admin, "real-1")
    with app.state.db.session() as s:
        s.add(models.Host(hostname="sim-1", api_key_hash="x", is_simulated=True, last_seen=utcnow()))
        s.commit()
    assert [h["hostname"] for h in client.get("/api/v1/hosts", headers=admin).json()] == ["real-1"]
    both = client.get("/api/v1/hosts?include_simulated=true", headers=admin).json()
    assert {h["hostname"]: h["is_simulated"] for h in both} == {"real-1": False, "sim-1": True}
    assert client.get("/api/v1/overview", headers=admin).json()["total"] == 1


def test_export_csv_json(client, admin):
    hid, key = register_host(client, admin)
    push(client, key, sample())
    r = client.get(f"/api/v1/hosts/{hid}/metrics/export?format=csv", headers=admin)
    assert r.status_code == 200 and r.text.splitlines()[0].startswith("ts,cpu_percent") and len(r.text.splitlines()) == 2
    assert len(client.get(f"/api/v1/hosts/{hid}/metrics/export?format=json", headers=admin).json()) == 1


def test_upgrade_flag(client, admin, app):
    _, key = register_host(client, admin)
    app.state.settings.latest_agent_version = "0.2.0"
    assert push(client, key, sample()).json()["upgrade_available"] is True


def test_simulator_seeds_flagged_data_and_purges(client, admin, app):
    from infrawatch_server import simulate
    from infrawatch_server.alerts import evaluate
    from infrawatch_server.models import utcnow
    register_host(client, admin, "real-1")
    simulate.seed(app.state.db, hosts=4, hours=2, interval=60)
    assert len(client.get("/api/v1/hosts", headers=admin).json()) == 1  # real data unaffected
    sim = client.get("/api/v1/hosts?include_simulated=true", headers=admin).json()
    assert len(sim) == 5 and sum(h["is_simulated"] for h in sim) == 4
    # simulated hosts cannot be authenticated as
    assert push(client, {"Authorization": f"Bearer iw_{sim[0]['id']}_guess"}, sample()).status_code == 401
    assert simulate.purge(app.state.db) == 4
    assert len(client.get("/api/v1/hosts?include_simulated=true", headers=admin).json()) == 1


def test_same_timestamp_twice_in_one_batch(client, admin):
    _, key = register_host(client, admin)
    s = sample()
    r = push(client, key, s, s).json()
    assert r["accepted"] == 1 and r["duplicates"] == 1
