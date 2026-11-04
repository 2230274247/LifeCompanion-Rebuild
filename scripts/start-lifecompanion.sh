#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA="$ROOT/infra"
RUNTIME="$INFRA/runtime"
LIFE_CORE="$ROOT/services/life-core"
GATEWAY="$ROOT/apps/product-portal"
CORE_PORT="${CORE_PORT:-8010}"
GATEWAY_PORT="${GATEWAY_PORT:-3001}"
CHAT_PORT="${CHAT_PORT:-3080}"
MEMOS_PORT="${MEMOS_PORT:-5230}"
PYTHON="${LIFE_PYTHON:-$LIFE_CORE/.venv/bin/python}"

for command_name in docker node curl; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing $command_name in PATH." >&2
    exit 1
  }
done
for required in "$INFRA/.env" "$ROOT/products/librechat-custom/.env" "$PYTHON"; do
  [[ -e "$required" ]] || {
    echo "Missing required file: $required" >&2
    exit 1
  }
done

mkdir -p "$RUNTIME"
set -a
# shellcheck disable=SC1091
source "$INFRA/.env"
# shellcheck disable=SC1091
source "$ROOT/products/librechat-custom/.env"
set +a

export LIFE_MEMOS_TOKENS_FILE="${LIFE_MEMOS_TOKENS_FILE:-$RUNTIME/memos-tokens.json}"
case "$LIFE_MEMOS_TOKENS_FILE" in
  /*) ;;
  *)
    echo "LIFE_MEMOS_TOKENS_FILE must be an absolute path." >&2
    exit 1
    ;;
esac
if [[ ! -f "$LIFE_MEMOS_TOKENS_FILE" ]]; then
  printf '{}\n' >"$LIFE_MEMOS_TOKENS_FILE"
  chmod 600 "$LIFE_MEMOS_TOKENS_FILE"
fi

export LIFE_LIBRECHAT_PORT="$CHAT_PORT"
export LIFE_MEMOS_PORT="$MEMOS_PORT"
export LIFE_CORE_HOST_URL="http://host.docker.internal:$CORE_PORT"
export MEMOS_BASE_URL="http://127.0.0.1:$MEMOS_PORT"
export LIFE_ALLOWED_ORIGINS="http://localhost:$GATEWAY_PORT,http://127.0.0.1:$GATEWAY_PORT"
export LIFE_PUBLIC_URL="http://127.0.0.1:$GATEWAY_PORT"
export LIFE_CHAT_INTERNAL_URL="http://127.0.0.1:$CHAT_PORT"
export LIFE_DATABASE_PATH="${LIFE_DATABASE_PATH:-$LIFE_CORE/data/life-core.sqlite3}"
export LIFE_HOST="127.0.0.1"
export LIFE_PORT="$CORE_PORT"
export PORT="$GATEWAY_PORT"
export CHAT_TARGET="http://127.0.0.1:$CHAT_PORT"
export LIFE_TARGET="http://127.0.0.1:$CORE_PORT"

is_healthy() {
  [[ "$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 3 "$1" || true)" == "200" ]]
}

port_open() {
  (echo >"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
}

wait_healthy() {
  local name="$1"
  local url="$2"
  local deadline=$((SECONDS + 90))
  while (( SECONDS < deadline )); do
    if is_healthy "$url"; then
      echo "[start] $name ready"
      return
    fi
    sleep 2
  done
  echo "$name did not become healthy: $url" >&2
  exit 1
}

echo "[start] starting upstream containers"
(
  cd "$INFRA"
  docker compose --env-file .env -f compose.baseline.yaml -f compose.spa.yaml up -d
)

if [[ -f "$INFRA/.env.reminders" ]]; then
  echo "[start] starting reminder containers"
  (
    cd "$INFRA"
    docker compose --env-file .env.reminders -f compose.reminders.yaml up -d
  )
fi

if ! is_healthy "http://127.0.0.1:$CORE_PORT/health"; then
  if port_open "$CORE_PORT"; then
    echo "Port $CORE_PORT is occupied by a non-healthy process." >&2
    exit 1
  fi
  (
    cd "$LIFE_CORE"
    nohup "$PYTHON" -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$CORE_PORT" \
      >"$RUNTIME/launcher-life-core.out.log" \
      2>"$RUNTIME/launcher-life-core.err.log" &
    echo $! >"$RUNTIME/launcher-life-core.pid"
  )
fi

if ! is_healthy "http://127.0.0.1:$GATEWAY_PORT/health"; then
  if port_open "$GATEWAY_PORT"; then
    echo "Port $GATEWAY_PORT is occupied by a non-healthy process." >&2
    exit 1
  fi
  (
    cd "$GATEWAY"
    nohup node server.mjs \
      >"$RUNTIME/launcher-gateway.out.log" \
      2>"$RUNTIME/launcher-gateway.err.log" &
    echo $! >"$RUNTIME/launcher-gateway.pid"
  )
fi

wait_healthy memos "http://127.0.0.1:$MEMOS_PORT/healthz"
wait_healthy librechat "http://127.0.0.1:$CHAT_PORT/health"
wait_healthy life-core "http://127.0.0.1:$CORE_PORT/health"
wait_healthy gateway "http://127.0.0.1:$GATEWAY_PORT/health"

echo "[start] complete: http://127.0.0.1:$GATEWAY_PORT"
