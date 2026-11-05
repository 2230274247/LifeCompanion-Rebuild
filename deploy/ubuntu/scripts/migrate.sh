#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# life-core creates/upgrades its SQLite schema on startup (Store.initialize).
# This wrapper restarts life-core so the schema reaches the current version,
# then verifies the store can be opened by the running service.
docker compose up -d life-core
sleep 2
docker compose exec -T life-core python - <<'PY'
from app.store import Store
from app.config import load_settings

settings = load_settings()
store = Store(settings.database_path)
store.initialize()
print("life-core database schema is up to date at", settings.database_path)
PY
echo "Migration check complete."
