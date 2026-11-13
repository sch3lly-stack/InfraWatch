# Roadmap

## Done (v0.1)
Server, ingestion, agent, auth/RBAC, alert engine (thresholds, sustained windows, suppression, cooldown, maintenance, ack/resolve/history),
webhook notifications, dashboard (overview, hosts, host detail, alerts, reports, settings), CSV/JSON export, custom checks (http/tcp/process),
environments/groups, agent registration + revocation, version reporting, simulator, Docker/Compose, CI, E2E tests.

## Not yet verified
* Run the full suite against PostgreSQL/TimescaleDB and `docker compose up` (workflows exist; needs a Docker-capable run).
* Agent on Linux/Windows hosts; systemd unit; Caddy TLS profile.

## Next
1. TimescaleDB continuous aggregates + `time_bucket` queries; compression and retention policies.
2. Slack/e-mail/PagerDuty notifiers; per-rule channel routing; re-notify while unacknowledged.
3. Multi-tenant extension (tenant_id on every table, tenant-scoped tokens/users).
4. Agent: multiple disks, per-process top-N (opt-in), signed self-update, Windows service wrapper.
5. SSO (OIDC), MFA, JWT revocation list, API tokens for automation.
6. Prometheus `/metrics` endpoint and OpenTelemetry export.
7. Alert grouping/escalation policies; anomaly baselines.
