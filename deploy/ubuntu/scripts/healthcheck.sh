#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

port="$(grep -E '^GATEWAY_PORT=' .env 2>/dev/null | cut -d= -f2- || true)"
port="${port:-3001}"
base="http://127.0.0.1:${port}"

check() {
  local name="$1" url="$2" expect="$3"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$url" 2>/dev/null || true)"
  if [[ "$code" == "$expect" ]]; then
    echo "OK   $name ($url -> $code)"
  else
    echo "FAIL $name ($url -> ${code:-timeout})"
    return 1
  fi
}

rc=0
check gateway "$base/health" 200 || rc=1
check life-core "$base/life-api/health" 200 || rc=1
# LibreChat root may redirect (302/200); only flag hard failures.
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$base/" 2>/dev/null || true)"
if [[ "$code" =~ ^(200|301|302|307|308)$ ]]; then
  echo "OK   librechat ($base/ -> $code)"
else
  echo "FAIL librechat ($base/ -> ${code:-timeout})"
  rc=1
fi

exit "$rc"
