#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Pull the latest committed code, rebuild, migrate, and restart while keeping
# all named volumes (accounts, memories, images and other business data) intact.
git pull --ff-only
docker compose build gateway life-core
./scripts/migrate.sh
docker compose up -d
./scripts/healthcheck.sh
echo "Update complete. User data and accounts were preserved."
