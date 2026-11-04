#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="$(dirname "$ROOT")"
UPSTREAM="$ROOT/products/librechat-custom"
PATCH="$ROOT/patches/librechat-v0.8.8-rebuild-p00-p07-20261104.patch"
BASE_COMMIT="e8f3be08623663d4ad7f7241e693c94469b63bb0"
SKIP_FRONTEND_BUILD="${SKIP_FRONTEND_BUILD:-0}"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing $1. $2" >&2
    exit 1
  }
}

copy_if_missing() {
  local source="$1"
  local destination="$2"
  if [[ -e "$destination" ]]; then
    echo "[bootstrap] kept existing $destination"
  else
    cp "$source" "$destination"
    echo "[bootstrap] created $destination"
  fi
}

initialize_env_secret() {
  local path="$1"
  local name="$2"
  local bytes="$3"
  local current
  local value
  local temporary

  current="$(awk -F= -v key="$name" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$path")"
  if [[ -n "$current" && "$current" != replace-* ]]; then
    return
  fi
  value="$(python3 -c 'import secrets, sys; print(secrets.token_hex(int(sys.argv[1])))' "$bytes")"
  temporary="${path}.tmp.$$"
  awk -v key="$name" -v value="$value" '
    BEGIN { found = 0 }
    $0 ~ "^[[:space:]]*" key "=" { print key "=" value; found = 1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$path" >"$temporary"
  mv "$temporary" "$path"
}

require_command git "Install Git first."
require_command node "Install Node.js 22.12 or newer."
require_command npm "Install npm first."
require_command python3 "Install Python 3.12 first."
require_command docker "Install Docker Engine and Compose first."

copy_if_missing "$ROOT/model_api_keys.env.example" "$PARENT/model_api_keys.env"
chmod 600 "$PARENT/model_api_keys.env"
copy_if_missing "$ROOT/.env.example" "$ROOT/infra/.env"
initialize_env_secret "$ROOT/infra/.env" "LIFE_INTERNAL_TOKEN" 32
initialize_env_secret "$ROOT/infra/.env" "JWT_SECRET" 32
initialize_env_secret "$ROOT/infra/.env" "JWT_REFRESH_SECRET" 32
initialize_env_secret "$ROOT/infra/.env" "CREDS_KEY" 32
initialize_env_secret "$ROOT/infra/.env" "CREDS_IV" 16
initialize_env_secret "$ROOT/infra/.env" "MEILI_MASTER_KEY" 32
initialize_env_secret "$ROOT/infra/.env" "MEMOS_BOOTSTRAP_ADMIN_PASSWORD" 32
chmod 600 "$ROOT/infra/.env"

if [[ ! -d "$UPSTREAM" ]]; then
  mkdir -p "$(dirname "$UPSTREAM")"
  git clone --branch v0.8.8 --single-branch \
    https://github.com/LibreChat-AI/LibreChat.git "$UPSTREAM"
  git -C "$UPSTREAM" checkout -b lifecompanion-baseline
fi

copy_if_missing "$UPSTREAM/.env.example" "$UPSTREAM/.env"

if [[ ! -f "$UPSTREAM/client/src/components/Life/Memories.tsx" ]]; then
  if [[ -n "$(git -C "$UPSTREAM" status --porcelain)" ]]; then
    echo "LibreChat working tree is dirty but is missing the LifeCompanion patch." >&2
    exit 1
  fi
  head="$(git -C "$UPSTREAM" rev-parse HEAD)"
  if [[ "$head" != "$BASE_COMMIT" ]]; then
    echo "LibreChat HEAD $head does not match patch base $BASE_COMMIT." >&2
    exit 1
  fi
  git -C "$UPSTREAM" apply --check "$PATCH"
  git -C "$UPSTREAM" apply "$PATCH"
  echo "[bootstrap] applied $PATCH"
else
  echo "[bootstrap] LifeCompanion upstream patch already present"
fi

if [[ "$SKIP_FRONTEND_BUILD" != "1" ]]; then
  (
    cd "$UPSTREAM"
    npm ci --ignore-scripts --no-audit --no-fund
    npm run frontend
  )
fi

VENV="$ROOT/services/life-core/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check \
  -r "$ROOT/services/life-core/requirements.txt"

echo "[bootstrap] complete"
echo "[bootstrap] fill only $PARENT/model_api_keys.env, then run scripts/start-lifecompanion.sh"
