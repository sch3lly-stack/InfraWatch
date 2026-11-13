# Roadmap

The authoritative plan is the GitHub tracker: milestones group issues by phase and every item has a priority label.
This page is a summary; if it disagrees with GitHub, GitHub wins.

| Milestone | Theme | Link |
|---|---|---|
| v0.1 Initial release | Core platform: server, agent, dashboard, alerting, security, docs, CI (delivered) | [milestone](https://github.com/sch3lly-stack/InfraWatch/milestones) |
| v0.2 Verification & hardening | Prove Postgres/Docker/Linux paths, Alembic, lint/type checks, coverage, Dependabot, governance & architecture docs | [issues](https://github.com/sch3lly-stack/InfraWatch/issues?q=is%3Aissue+milestone%3A%22v0.2+-+Verification+%26+hardening%22) |
| v0.3 Scale & integrations | time_bucket/aggregates, more notifiers, UI management, agent health, pagination, Windows | [issues](https://github.com/sch3lly-stack/InfraWatch/issues?q=is%3Aissue+milestone%3A%22v0.3+-+Scale+%26+integrations%22) |
| v1.0 Production ready | Multi-tenancy, SSO/MFA, token revocation, signed agent updates, release automation | [issues](https://github.com/sch3lly-stack/InfraWatch/issues?q=is%3Aissue+milestone%3A%22v1.0+-+Production+ready%22) |

## Known unverified areas
`docker compose up` and the Caddy TLS profile (#2), hypertable creation assertions (#1), the agent on Linux (#3) and Windows (#4).
