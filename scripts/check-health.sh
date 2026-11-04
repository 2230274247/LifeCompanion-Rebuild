#!/usr/bin/env bash
set -euo pipefail

GATEWAY_PORT="${GATEWAY_PORT:-3001}"
CORE_PORT="${CORE_PORT:-8010}"
CHAT_PORT="${CHAT_PORT:-3080}"
MEMOS_PORT="${MEMOS_PORT:-5230}"
failed=0

check() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --max-time 8 "$url" || true)"
  if [[ "$code" == "200" ]]; then
    printf 'PASS %-10s %s\n' "$name" "$url"
  else
    printf 'FAIL %-10s %s http_status=%s\n' "$name" "$url" "${code:-unavailable}"
    failed=1
  fi
}

check gateway "http://127.0.0.1:${GATEWAY_PORT}/health"
check life-core "http://127.0.0.1:${CORE_PORT}/health"
check librechat "http://127.0.0.1:${CHAT_PORT}/health"
check memos "http://127.0.0.1:${MEMOS_PORT}/healthz"

exit "$failed"
