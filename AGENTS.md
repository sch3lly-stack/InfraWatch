# AGENTS.md: Permanent engineering rules for InfraWatch

This file is the authoritative operating manual for every contributor and AI agent working in this repository.
**Read it at the start of every development session.** It lives in the repository root, is version controlled, and must
never be deleted, ignored (`.gitignore`) or replaced without explicit authorization from the repository owner.
Update it (through a PR) whenever the engineering procedure changes. Any other agent instruction file must stay consistent with it.

The goal is not only working software but a development history that shows professional engineering discipline.
**Every meaningful change must be traceable: Issue → branch → commits → pull request → tests/CI → merge → closed issue.**

## 1. Session start checklist
1. Read this file.
2. `git status`, `git fetch`, check the current branch (never work on `main`).
3. `gh issue list`: open issues; `gh pr list`: open PRs; `gh run list`: failing CI.
4. Identify incomplete work, blocked tasks (`status:blocked`) and dependencies.
5. Pick the next task by priority (`priority:critical` → `low`) and dependency order, within the current milestone.
6. Make sure an issue exists for the work *before* branching. If not, create it (no duplicates: search first).

## 2. Issues
Every feature, bug fix, refactor, security change, infrastructure change or documentation task has an issue containing:
objective, background/technical context, scope, acceptance criteria, dependencies, testing requirements, Definition of Done, labels and priority
(use the issue forms in `.github/ISSUE_TEMPLATE`).

* **Labels**: one `type:*` (`feature`, `bug`, `refactor`, `security`, `documentation`, `testing`, `infrastructure`), one `priority:*`
  (`critical`, `high`, `medium`, `low`), optional `area:*` (`backend`, `frontend`, `agent`, `ci`), `status:blocked`, `status:partial`.
* **Milestones** are release phases: v0.1 (initial), v0.2 (verification & hardening), v0.3 (scale & integrations), v1.0 (production ready).
* Retroactive issues must say they were created retroactively. Never backdate or misrepresent history. Never close an issue for incomplete work;
  partially complete work stays open, is labelled `status:partial` and lists what remains.
* Project board: **blocked**: the CLI token lacks the `project` scope (`gh auth refresh -s project` must be run by the owner). Milestones + labels are the tracking
  system until a board exists.

## 3. Branching
Never commit to `main` directly. Branch from an up-to-date `main`, keep branches short-lived and focused:

`feature/<issue>-<slug>`, `bugfix/<issue>-<slug>`, `hotfix/<issue>-<slug>`, `refactor/<issue>-<slug>`, `docs/<issue>-<slug>`,
`test/<issue>-<slug>`, `security/<issue>-<slug>`, `infra/<issue>-<slug>`. Example: `feature/10-rule-editing-ui`.

## 4. Commits
Conventional Commits, referencing the issue in the body or footer:
`feat(auth): implement role-based access control`, `fix(api): correct invalid pagination handling`, `test(agent): add reconnect tests`,
`docs(architecture): document ingest flow`, `ci:`, `refactor:`, `chore:`. Breaking changes use `!` / `BREAKING CHANGE:`. Semantic Versioning for releases.
Commits made by an AI agent end with the attribution trailer the harness specifies.

## 5. Pull requests
Every meaningful change goes through a PR (use `.github/PULL_REQUEST_TEMPLATE.md`). The PR must: reference the issue (`Closes #N`), explain what and why,
summarise implementation, list affected components, list testing performed, document risks, include screenshots for UI changes and migration notes for DB changes.
Do not bundle unrelated changes.

## 6. Self-review and merge (autonomous, never misrepresented)
Agents may complete their own PRs but must not pretend independent review happened. Do **not** approve your own PR from another account; post an
**engineering self-review comment** instead. If an independent reviewer is available, use GitHub's real review feature. Before merging:

1. Read the full diff; check for unintended files, secrets, duplicated or dead code.
2. Verify every acceptance criterion; consider security implications.
3. Run locally and record results in the PR: Python `ruff check`, `mypy` (once #35 lands), `pytest server/tests`, `pytest agent/tests`, `pytest tests/integration`;
   frontend `npm run build`, `npx playwright test` (and lint/unit tests once #7 lands).
4. Review migrations when schemas change.
5. Required GitHub Actions checks are green; no merge conflicts; no unresolved blocking comments.
6. Fix findings on the same branch and repeat.
7. **Squash merge** (`gh pr merge --squash --delete-branch`) with a Conventional-Commit title; verify the merge and that the issue closed.

Never bypass branch protection, required reviews, failing checks or security policies. If blocked, report the exact blocker and leave the PR open.

## 7. Definition of Done
Implementation finished · acceptance criteria met · relevant tests pass with no regressions · code reviewed · documentation updated (README, docs, CHANGELOG,
ADR if a significant decision was made) · required CI green · PR merged · issue closed. Anything less is not done.

## 8. Documentation upkeep
Keep current: README.md, AGENTS.md, CHANGELOG.md (Keep a Changelog), CONTRIBUTING.md, SECURITY.md, docs/ARCHITECTURE.md, docs/API.md, docs/DATABASE.md,
docs/ROADMAP.md. Record significant architectural decisions as ADRs in `docs/adr/`.

## 9. Engineering standards
* Tests for every behaviour change; bug fixes start with a failing test. Never hide failing tests or unresolved security concerns.
* Security: validate input at boundaries, no secrets in code/logs/commits (`.env` is git-ignored), least privilege, audit significant actions, keep the agent's
  data collection minimal (no files, user names or command lines).
* Database changes use migrations once Alembic lands (#5); until then, note schema changes explicitly in the PR.
* Structured JSON logging; no sensitive values in logs.
* Simulated data stays flagged `is_simulated` and separate from real data. Do not claim a host is monitored unless its agent has actually reported.
* Report outcomes truthfully: say what was verified and what was not.

## 10. Project commands
```bash
# setup
python3 -m venv .venv && . .venv/bin/activate && pip install -e "server[dev]" -e "agent[dev]" ruff
cd frontend && npm ci && npx playwright install chromium

# test (run suites separately: each has its own conftest.py)
pytest server/tests ; pytest agent/tests ; pytest tests/integration
cd frontend && npm run build && npx playwright test        # PYTHON=.venv/bin/python is picked up by scripts/e2e_server.sh
ruff check server agent tests                                # config arrives in #35
```
Server tests run on SQLite by default; set `INFRAWATCH_TEST_DATABASE_URL=postgresql://…` for PostgreSQL.

## 11. Stop and report before
Deleting important user data · destructive production DB operations · exposing private information · changing repository ownership or access permissions ·
disabling security controls · bypassing branch protection · adding paid services or financial commitments · irreversible production deployments.
Routine implementation decisions do **not** require asking.

## 12. Known deviations from this process (history)
The initial code (commit `f13e87c`) was pushed directly to `main` before this workflow existed. The issues for that work (#22 to #32) were created
retroactively and say so.
