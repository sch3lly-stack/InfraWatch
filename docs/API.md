# API

OpenAPI/Swagger: `GET /api/docs`. All paths are under `/api/v1`. Dashboard routes need `Authorization: Bearer <JWT>`,
agent routes need the agent's API key (or enrollment token for `register`). Errors are `{"detail": "..."}`.

## Auth
```bash
curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"admin","password":"..."}'          # -> {"access_token": "...", "role": "admin"}
```

## Agent endpoints
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/agents/register` | enrollment token | body: hostname, os, os_version, arch, agent_version -> `{host_id, api_key}` (once) |
| POST | `/agents/metrics` | agent key | batch ingest, ≤ 500 samples; returns `accepted/duplicates/rejected/upgrade_available` |
| GET | `/agents/whoami` | agent key | credential check |

```json
POST /agents/metrics
{"agent": {"agent_version": "0.1.0", "collection_interval": 15},
 "samples": [{"ts": "2026-01-01T12:00:00+00:00",
   "system": {"cpu_percent": 12.5, "mem_percent": 41.0, "disk_percent": 63.2, "net_sent_bps": 1200, "uptime_seconds": 86400},
   "checks": [{"name": "web", "kind": "http", "target": "http://localhost/health", "ok": true, "response_ms": 14.2, "status_code": 200}]}]}
```

## Dashboard endpoints
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/overview` | viewer | totals; `?environment=&include_simulated=` |
| GET | `/hosts` | viewer | `?environment=&group=&status=&search=&include_simulated=` |
| GET/PATCH/DELETE | `/hosts/{id}` | viewer / admin | PATCH: environment, group, revoked |
| GET | `/hosts/{id}/metrics` | viewer | `?range=15m|1h|6h|24h|7d|30d` or `start`/`end`, `max_points` (downsampled) |
| GET | `/hosts/{id}/metrics/export` | viewer | `?format=csv|json&range=` |
| GET | `/hosts/{id}/services` | viewer | availability, avg response, history |
| GET | `/reports/summary` | viewer | per-host avg/max, availability, alert count |
| GET | `/alerts` | viewer | `?status=active|open|acknowledged|resolved&severity=&host_id=` |
| POST | `/alerts/{id}/acknowledge`, `/resolve` | operator | 409 on invalid state transition |
| CRUD | `/rules` | viewer read / admin write | |
| CRUD | `/channels` | admin | webhook channels |
| CRUD | `/maintenance` | viewer read / operator write | |
| GET/POST | `/enrollment-tokens` | admin | token value returned once |
| GET/POST/PATCH | `/users` | admin | |
| GET | `/audit` | admin | |
| GET | `/health` | none | liveness |

Webhook payload: `{"event": "alert.opened|alert.resolved", "alert": {id, title, message, severity, status, host, environment, value, opened_at}}`.
