#!/usr/bin/env bash
# Starts a throwaway InfraWatch server (fresh SQLite DB + simulated data) for Playwright.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
DB="$(mktemp -d)/e2e.db"
export INFRAWATCH_DATABASE_URL="sqlite:///$DB"
export INFRAWATCH_SECRET_KEY="e2e-secret-key-e2e-secret-key-e2e-secret"
export INFRAWATCH_ADMIN_PASSWORD="e2e-admin-password"
export INFRAWATCH_FRONTEND_DIR="$ROOT/frontend/dist"
export INFRAWATCH_RATE_LIMIT_LOGIN_PER_MIN=1000
"$PY" -m infrawatch_server.simulate --hosts 6 --hours 6
exec "$PY" -m uvicorn --factory infrawatch_server.main:app_factory --port "${PORT:-8765}"
