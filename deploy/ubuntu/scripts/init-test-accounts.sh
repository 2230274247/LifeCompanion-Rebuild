#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

port="$(grep -E '^GATEWAY_PORT=' .env 2>/dev/null | cut -d= -f2- || true)"
base="http://127.0.0.1:${port:-3001}"

register() {
  local name="$1" username="$2" email="$3" password="$4"
  local code
  code="$(curl -s -o /tmp/lc-register.json -w '%{http_code}' --max-time 15 \
    -X POST "$base/api/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$name\",\"username\":\"$username\",\"email\":\"$email\",\"password\":\"$password\",\"confirm_password\":\"$password\"}")"
  if [[ "$code" != "200" ]]; then
    echo "WARN: register $username failed (HTTP $code): $(head -c 200 /tmp/lc-register.json)" >&2
    return 1
  fi
  echo "Registered $username."
}

admin_pass="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-16)"
user_pass="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-16)"

register "拾光管理员" "shiguang-admin" "shiguang-admin@example.com" "$admin_pass" || true
register "拾光用户" "shiguang-user1" "shiguang-user1@example.com" "$user_pass" || true

umask 077
cat > test-accounts.env <<EOF
ADMIN_USERNAME=shiguang-admin
ADMIN_EMAIL=shiguang-admin@example.com
ADMIN_PASSWORD=$admin_pass
USER_USERNAME=shiguang-user1
USER_EMAIL=shiguang-user1@example.com
USER_PASSWORD=$user_pass
EOF
chmod 600 test-accounts.env
echo "Test credentials written to test-accounts.env (chmod 600)."
echo "To grant the admin account moment direct-test privileges, set in .env:"
echo "  LIFE_DIRECT_MOMENT_TEST_ENABLED=true"
echo "  LIFE_DIRECT_MOMENT_TEST_USERNAME=shiguang-admin"
