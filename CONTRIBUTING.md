# Contributing to InfraWatch

Thanks for helping! The full engineering rules are in [AGENTS.md](AGENTS.md); this is the short version.

## Workflow
1. Find or open an issue (use the templates). Comment to claim it.
2. Branch from `main`: `feature/<issue>-<slug>` (also `bugfix/`, `hotfix/`, `refactor/`, `docs/`, `test/`, `security/`, `infra/`).
3. Commit with [Conventional Commits](https://www.conventionalcommits.org/): `feat(agent): add multi-disk support`.
4. Open a PR using the template; include `Closes #<issue>`, testing evidence and screenshots for UI changes.
5. CI must pass; PRs are squash-merged.

## Development setup
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "server[dev]" -e "agent[dev]" ruff
(cd frontend && npm ci && npx playwright install chromium)
```

## Running checks
```bash
pytest server/tests          # SQLite by default
pytest agent/tests
pytest tests/integration     # real agent <-> real server incl. TLS
ruff check server agent tests
cd frontend && npm run build && npx playwright test
```
PostgreSQL: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=ci timescale/timescaledb:latest-pg16` then
`INFRAWATCH_TEST_DATABASE_URL=postgresql://postgres:ci@localhost:5432/postgres pytest server/tests` (the suite drops and recreates tables, so use a throwaway DB).

## Standards
* Add or update tests with every behaviour change; bug fixes start with a failing test.
* Keep PRs focused; update docs and CHANGELOG (`Unreleased`) in the same PR.
* Never commit secrets. Report vulnerabilities privately, see [SECURITY.md](SECURITY.md).
* Significant design decisions get an ADR in `docs/adr/`.

## Versioning and releases
Semantic Versioning. Releases are tagged from `main`; see [CHANGELOG.md](CHANGELOG.md) and issue #21 for the release automation.
