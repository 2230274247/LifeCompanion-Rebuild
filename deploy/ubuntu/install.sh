#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed." >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin is not installed." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "No .env found; creating one from .env.example with generated secrets."
  cp .env.example .env
  # Generate strong defaults for the required secrets.
  sed -i "s/change_me_64_hex/$(openssl rand -hex 32)/g" .env
  sed -i "s/change_me_16_hex/$(openssl rand -hex 16)/g" .env
  sed -i "s/change_me_32_hex/$(openssl rand -hex 32)/g" .env
  sed -i "s/change_me_long_random/$(openssl rand -hex 48)/g" .env
  sed -i "s/change_me/$(openssl rand -hex 32)/g" .env
  echo "Generated .env. Edit DEEPSEEK_API_KEY and any optional keys before starting."
else
  echo "Using existing .env."
fi

chmod 600 .env

if [[ ! -d librechat-custom/client/dist ]]; then
  echo "ERROR: librechat-custom build artifacts are missing." >&2
  echo "Run deploy/ubuntu/build-librechat.sh on a machine with Node 24 first," >&2
  echo "or unpack the prebuilt release bundle." >&2
  exit 1
fi

./scripts/preflight.sh

docker compose up -d --build

echo "Bootstrapping ntfy admin user (life-core uses its HTTP admin API for per-user push)."
NTFY_ADMIN_USER="$(grep -E '^LIFE_NTFY_ADMIN_USER=' .env | cut -d= -f2-)"
NTFY_ADMIN_PASSWORD="$(grep -E '^LIFE_NTFY_ADMIN_PASSWORD=' .env | cut -d= -f2-)"
if [[ -n "${NTFY_ADMIN_USER}" && -n "${NTFY_ADMIN_PASSWORD}" ]]; then
  docker compose exec -T ntfy sh -c \
    'NTFY_PASSWORD="$1" ntfy user add --role=admin "$2"' \
    _ "${NTFY_ADMIN_PASSWORD}" "${NTFY_ADMIN_USER}" \
    || echo "WARN: ntfy admin bootstrap failed (it may already exist)."
fi

./scripts/healthcheck.sh
echo "LifeCompanion stack is up."
