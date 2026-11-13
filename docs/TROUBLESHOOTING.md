# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Host stays **Pending** | The agent has never reported. Run `infrawatch-agent check`; look at its JSON logs for `registration failed` / `send failed`. |
| `cannot reach server: ConnectError` / `ConnectTimeout` | Wrong `server_url`, firewall, or server down. Samples are buffered meanwhile (`infrawatch-agent status` shows `buffered_samples`). |
| `SSLCertVerificationError` / `ConnectError` on https | Server uses a private CA or self-signed cert. Set `ca_bundle: /path/ca.pem`. Verification can't be turned off by design. |
| `configuration error: server_url must use https` | Plain HTTP is only allowed to localhost. Use HTTPS or `allow_insecure_http: true` for lab use. |
| `registration failed … invalid, used or expired enrollment token` | Tokens are single-use and expire (default 1 h). Create a new one. |
| `server rejected credentials` | The host was revoked or the key file doesn't match. Delete `state_dir/agent.key` and re-register with a new token (this creates a new host record). |
| Host flapping Online/Offline | Collection `interval` close to or above `OFFLINE_AFTER_SECONDS`, or the agent is in backoff after errors. Raise `INFRAWATCH_OFFLINE_AFTER_SECONDS` to ≥ 3× interval. |
| 429 responses | Rate limit hit (login 10/min/IP, ingest 120/min/host by default). Agents back off automatically; tune `INFRAWATCH_RATE_LIMIT_*`. Behind a proxy set `TRUST_PROXY_HEADERS=true`, otherwise all users share the proxy IP. |
| Dashboard shows no data but agent is fine | "Show simulated data" only toggles simulated hosts; real hosts need ≥ 1 accepted sample. Check the time range. |
| No alert notifications | Check channel `min_severity`; webhook URLs resolving to private IPs need `ALLOW_PRIVATE_WEBHOOKS=true`; look for `notification to channel … failed` in server logs. Alerts inside a maintenance window are suppressed. |
| Alert did not re-open after I resolved it | Cooldown: the rule's `cooldown_seconds` blocks re-opening the same alert after resolution. |
| Server logs `Created initial admin … generated password` | Set `INFRAWATCH_ADMIN_PASSWORD` before first start. |
| Sessions reset on restart | `INFRAWATCH_SECRET_KEY` not set (ephemeral key generated). |
| Compose: `set POSTGRES_PASSWORD in .env` | Copy `.env.example` to `.env` and fill in values. |
