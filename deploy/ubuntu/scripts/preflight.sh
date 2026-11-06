#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

fail=0
require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $1" >&2
    fail=1
  fi
}
require docker
require openssl

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin missing." >&2
  fail=1
fi

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. Run ./install.sh or copy .env.example to .env." >&2
  fail=1
else
  if grep -q 'change_me' .env; then
    echo "ERROR: .env still contains placeholder values (change_me)." >&2
    fail=1
  fi
fi

for path in \
  librechat-custom/librechat.yaml \
  librechat-custom/api/server/middleware/canDeleteAccount.js \
  librechat-custom/api/server/controllers/AuthController.js \
  librechat-custom/api/server/services/AuthService.js \
  librechat-custom/api/strategies/validators.js \
  librechat-custom/api/strategies/localStrategy.js \
  librechat-custom/api/app/clients/BaseClient.js \
  librechat-custom/client/dist/index.html \
  librechat-custom/packages/api/dist \
  librechat-custom/packages/data-provider/dist; do
  if [[ ! -e "$path" ]]; then
    echo "ERROR: missing LibreChat custom artifact: $path" >&2
    fail=1
  fi
done

# Confirm the host architecture can run the pinned linux/amd64 images.
if [[ "$(uname -m)" != "x86_64" ]]; then
  echo "WARN: host is $(uname -m); pinned images are linux/amd64 and may need emulation." >&2
fi

if [[ "$fail" -ne 0 ]]; then
  echo "Preflight failed." >&2
  exit 1
fi
echo "Preflight OK."
