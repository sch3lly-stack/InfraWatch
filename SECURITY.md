# Security Policy

## Reporting a vulnerability
Please **do not open a public issue**. Report privately through GitHub:
<https://github.com/sch3lly-stack/InfraWatch/security/advisories/new>. Include affected version/commit, reproduction steps and impact.
Expect an acknowledgement within a few days. This is a portfolio/learning project without a formal SLA or supported-versions matrix yet (see roadmap).

## Security design

## Threat model (summary)
Agents run on semi-trusted hosts and talk to the server over the network; operators use the dashboard.
Goals: a compromised or malicious agent can only write metrics *for itself*; an unauthenticated party can read or write nothing;
an operator can only do what their role allows.

## Controls
| Concern | Implementation |
|---|---|
| Agent registration | Admin-created **enrollment tokens**: random 192-bit, expiring, **single use**, stored only as SHA-256. Register attempts (including failures) are audited and rate limited. |
| Agent authentication | Per-host API key `iw_<host_id>_<256-bit secret>`, shown once, only SHA-256 stored, compared in constant time. Revocable. |
| No impersonation | The host identity comes **only** from the key. The ingest schema forbids extra fields (`extra=forbid`), so there is no host-id field to forge; swapping ids with another host's secret fails (tested). Simulated hosts have unguessable key hashes. |
| Transport | Agent refuses `http://` servers except localhost; TLS verification can't be disabled, only a custom CA can be supplied. Caddy TLS profile provided. |
| Dashboard auth | Argon2id passwords, constant-time-ish login (dummy hash for unknown users), JWT (HS256, 8 h). Role and disabled status are re-read from DB on every request, so demotion is immediate. |
| RBAC | viewer: read. operator: + ack/resolve/maintenance. admin: + rules, channels, tokens, users, host management, audit log. |
| Input validation | Pydantic models with bounds, regexes and `extra=forbid`; batch size, clock-skew (±5 min) and sample-age limits; parametrised queries via SQLAlchemy (no string SQL). |
| Rate limiting | Per-IP for login/register/API, per-host for ingest. Returns 429 + Retry-After. |
| Secrets | All via environment (`.env` is git-ignored); compose refuses to start without them; agent key file is 0600; secrets are never logged except the one-time generated admin password if none is configured. |
| Audit log | Logins (incl. failures), registrations, rule/channel/user/host/maintenance changes, ack/resolve, exports. Admin-viewable. |
| Webhooks / SSRF | URLs must be http(s) and resolve to public addresses unless `ALLOW_PRIVATE_WEBHOOKS=true`; redirects are not followed; short timeouts. |
| Browser | CSP, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, `Cache-Control: no-store` on API; React escapes output (no `dangerouslySetInnerHTML`). Token kept in `sessionStorage`. |
| Data minimisation | Agent collects aggregate resource counters only. It never reads files, user names, command lines or environment; process checks compare names only. |
| Containers | Non-root user, read-only filesystem, all capabilities dropped, `no-new-privileges`. systemd unit is sandboxed. |

## OWASP Top 10 mapping
A01 Broken access control → RBAC deps on every route + tests. A02 Crypto failures → Argon2id, TLS, hashed keys.
A03 Injection → ORM + validation. A04 Insecure design → one-time tokens, key-derived identity. A05 Misconfiguration →
required secrets, headers, hardened containers. A06 Vulnerable components → `pip-audit`, `bandit`, `npm audit` workflow.
A07 Auth failures → rate limiting, audit, Argon2. A08 Integrity → hashed, single-use enrollment. A09 Logging → audit log + structured logs.
A10 SSRF → webhook URL validation.

## Known gaps (be honest before production use)
* No MFA/SSO; JWTs cannot be individually revoked before expiry (but user disable/role change is immediate).
* Rate limiter is per process. Put a shared limiter at the proxy for multi-replica setups.
* The webhook SSRF check resolves DNS at validation time and again at send time (DNS-rebinding window remains). Prefer allow-listing egress.
* No agent-binary signing/auto-update; version management is reporting + `upgrade_available` flag.
* Metrics rows are not signed; a compromised host can falsify its **own** data (by design cannot affect others).

Report vulnerabilities privately to the maintainers rather than opening a public issue.
