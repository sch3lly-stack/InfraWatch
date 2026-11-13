from datetime import datetime, timedelta, timezone

from conftest import login, make_user, push, register_host, sample


def test_unauthenticated_api_rejected(client):
    for path in ["/api/v1/hosts", "/api/v1/alerts", "/api/v1/rules", "/api/v1/overview", "/api/v1/users"]:
        assert client.get(path).status_code == 401


def test_login_failure_and_audit(client, admin):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401
    log = client.get("/api/v1/audit", headers=admin).json()
    assert any(e["action"] == "auth.login_failed" for e in log)


def test_login_rate_limited(client):
    codes = [client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad"}).status_code
             for _ in range(12)]
    assert 429 in codes


def test_role_permissions(client, admin):
    viewer = make_user(client, admin, "viewer")
    operator = make_user(client, admin, "operator")
    assert client.get("/api/v1/hosts", headers=viewer).status_code == 200
    rule = {"name": "cpu", "type": "cpu_high", "threshold": 90}
    assert client.post("/api/v1/rules", json=rule, headers=viewer).status_code == 403
    assert client.post("/api/v1/rules", json=rule, headers=operator).status_code == 403
    assert client.post("/api/v1/rules", json=rule, headers=admin).status_code == 201
    assert client.get("/api/v1/users", headers=operator).status_code == 403
    assert client.post("/api/v1/enrollment-tokens", json={}, headers=operator).status_code == 403
    assert client.get("/api/v1/audit", headers=viewer).status_code == 403


def test_disabled_user_loses_access_immediately(client, admin):
    viewer = make_user(client, admin, "viewer")
    uid = [u for u in client.get("/api/v1/users", headers=admin).json() if u["username"] == "user_viewer"][0]["id"]
    client.patch(f"/api/v1/users/{uid}", json={"disabled": True}, headers=admin)
    assert client.get("/api/v1/hosts", headers=viewer).status_code == 401


def test_admin_cannot_demote_self(client, admin):
    uid = client.get("/api/v1/users", headers=admin).json()[0]["id"]
    assert client.patch(f"/api/v1/users/{uid}", json={"role": "viewer"}, headers=admin).status_code == 409


def test_tampered_jwt_rejected(client, admin):
    bad = {"Authorization": admin["Authorization"][:-3] + "abc"}
    assert client.get("/api/v1/hosts", headers=bad).status_code == 401


def test_enrollment_token_single_use_and_expiry(client, admin):
    t = client.post("/api/v1/enrollment-tokens", json={"ttl_minutes": 5}, headers=admin).json()
    h = {"Authorization": f"Bearer {t['token']}"}
    body = {"hostname": "a"}
    assert client.post("/api/v1/agents/register", json=body, headers=h).status_code == 201
    assert client.post("/api/v1/agents/register", json=body, headers=h).status_code == 401  # reuse
    assert client.post("/api/v1/agents/register", json=body,
                       headers={"Authorization": "Bearer iwe_bogus"}).status_code == 401
    assert client.post("/api/v1/agents/register", json=body).status_code == 401


def test_enrollment_token_not_stored_in_plaintext(client, admin):
    t = client.post("/api/v1/enrollment-tokens", json={}, headers=admin).json()
    listed = client.get("/api/v1/enrollment-tokens", headers=admin).json()
    assert t["token"] not in str(listed)


def test_agent_cannot_impersonate_other_host(client, admin):
    id_a, key_a = register_host(client, admin, "host-a")
    id_b, key_b = register_host(client, admin, "host-b")
    # Payload has no host identifier; extra fields are rejected outright.
    r = client.post("/api/v1/agents/metrics", json={"host_id": id_b, "samples": [sample()]}, headers=key_a)
    assert r.status_code == 422
    assert push(client, key_a, sample(cpu=11)).status_code == 200
    h = {h["id"]: h for h in client.get("/api/v1/hosts?include_simulated=true", headers=admin).json()}
    assert h[id_a]["latest"]["cpu_percent"] == 11
    assert h[id_b].get("latest") is None
    # Forged key: A's secret with B's id
    secret_a = key_a["Authorization"].split("_", 2)[2]
    forged = {"Authorization": f"Bearer iw_{id_b}_{secret_a}"}
    assert push(client, forged, sample()).status_code == 401


def test_agent_key_cannot_use_dashboard_api_and_vice_versa(client, admin):
    _, key = register_host(client, admin)
    assert client.get("/api/v1/hosts", headers=key).status_code == 401
    assert push(client, admin, sample()).status_code == 401


def test_revoked_agent_rejected(client, admin):
    hid, key = register_host(client, admin)
    assert push(client, key, sample()).status_code == 200
    client.patch(f"/api/v1/hosts/{hid}", json={"revoked": True}, headers=admin)
    assert push(client, key, sample()).status_code == 401


def test_input_validation(client, admin):
    _, key = register_host(client, admin)
    bad = sample(cpu=250)
    assert push(client, key, bad).status_code == 422
    naive = sample()
    naive["ts"] = datetime.now().replace(tzinfo=None).isoformat()
    assert push(client, key, naive).status_code == 422
    assert client.post("/api/v1/agents/metrics", json={"samples": []}, headers=key).status_code == 422
    assert client.post("/api/v1/rules", json={"name": "x", "type": "cpu_high"}, headers=admin).status_code == 422
    assert client.post("/api/v1/rules", json={"name": "x", "type": "cpu_high", "threshold": 500}, headers=admin).status_code == 422
    assert client.get("/api/v1/hosts/1/metrics?range=bogus", headers=admin).status_code in (404, 422)


def test_webhook_url_validation(client, admin, app):
    app.state.settings.allow_private_webhooks = False
    r = client.post("/api/v1/channels", json={"name": "x", "url": "http://127.0.0.1:9/hook"}, headers=admin)
    assert r.status_code == 422
    r = client.post("/api/v1/channels", json={"name": "x", "url": "file:///etc/passwd"}, headers=admin)
    assert r.status_code == 422


def test_security_headers(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
