#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d
echo "Containers started. Use ./scripts/healthcheck.sh to verify."
