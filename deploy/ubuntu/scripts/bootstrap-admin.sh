#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

admin_email="${1:-admin@shiguang.test}"

source_env() {
  grep -E "^${1}=" .env 2>/dev/null | tail -n1 | cut -d= -f2- || true
}

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found. Run install.sh first." >&2
  exit 1
fi

internal_token="$(source_env LIFE_INTERNAL_TOKEN)"
gateway_port="$(source_env GATEWAY_PORT)"
gateway_port="${gateway_port:-3001}"

if [[ -z "$internal_token" ]]; then
  echo "ERROR: LIFE_INTERNAL_TOKEN is empty in .env" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose is required." >&2
  exit 1
fi

echo "Looking up LibreChat account with email: $admin_email"
raw="$(docker compose exec -T mongo mongosh --quiet --eval \
  "const u=db.getSiblingDB('LibreChat').users.findOne({email:'${admin_email}'},{_id:1,username:1,name:1}); if(!u){quit(1)} print(JSON.stringify({id:u._id.toString(),username:u.username||'',name:u.name||''}))" \
  || { echo "ERROR: account not found in LibreChat MongoDB." >&2; exit 1; })"

parse() {
  printf '%s' "$raw" | python3 -c "import sys,json; print(json.load(sys.stdin)['$1'])"
}

id="$(parse id)"
username="$(parse username)"
name="$(parse name)"

if [[ -z "$id" || -z "$username" ]]; then
  echo "ERROR: could not resolve admin account (id or username missing)." >&2
  echo "Raw mongosh output: $raw" >&2
  exit 1
fi

echo "Resolved LibreChat user: id=$id username=$username name=$name"

payload="$(python3 - "$id" "$username" "$name" <<'PY'
import json, sys
print(json.dumps({
    "librechat_user_id": sys.argv[1],
    "memos_user_id": f"users/{sys.argv[2]}",
    "memos_username": sys.argv[2],
    "display_name": sys.argv[3] or sys.argv[2],
    "memory_consent": True,
    "image_consent": True,
}))
PY
)"

code="$(curl -s -o /tmp/lc-bootstrap-admin.json -w '%{http_code}' --max-time 15 \
  -X POST http://127.0.0.1:8010/internal/v1/users/bootstrap \
  -H "X-Internal-Token: $internal_token" \
  -H 'Content-Type: application/json' \
  --data-binary "$payload")"
if [[ "$code" != "200" ]]; then
  echo "ERROR: life-core bootstrap failed (HTTP $code): $(head -c 300 /tmp/lc-bootstrap-admin.json)" >&2
  exit 1
fi

set_env() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '\n%s=%s\n' "$key" "$value" >> .env
  fi
}

set_env LIFE_DIRECT_MOMENT_TEST_ENABLED true
set_env LIFE_DIRECT_MOMENT_TEST_USERNAME "$username"
set_env LIFE_DIRECT_MOMENT_TEST_USER_ID "$id"
set_env LIFE_DIRECT_MOMENT_TEST_UNLIMITED true

echo "Recreating life-core with the updated environment..."
docker compose up -d --force-recreate --no-deps life-core

echo "Waiting for life-core to become ready..."
for _ in $(seq 1 20); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8010/health 2>/dev/null || true)" == "200" ]]; then
    break
  fi
  sleep 1
done

echo "Bootstrap complete."
echo "Verify life-core health:"
echo "  curl -s http://127.0.0.1:${gateway_port}/life-api/health"
echo "Then log in as $admin_email and open a chat; the admin test card should appear."
