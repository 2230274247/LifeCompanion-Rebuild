#!/usr/bin/env bash
# Builds deploy/ubuntu/librechat-custom from the archived V0.3 patch.
# Requirements: Node 24+, npm, git. Run from the repository root:
#   bash deploy/ubuntu/build-librechat.sh
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

patch="patches/librechat-v0.8.8-v03-collaboration-20261106.patch"
base_commit="e8f3be08623663d4ad7f7241e693c94469b63bb0"
work=".work/librechat-build"
out="deploy/ubuntu/librechat-custom"

if ! command -v node >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
  echo "ERROR: node and git are required." >&2
  exit 1
fi

rm -rf "$work"
mkdir -p "$work"
git clone --filter=blob:none --no-checkout https://github.com/danny-avila/LibreChat.git "$work"
git -C "$work" checkout "$base_commit"
git -C "$work" apply "$repo_root/$patch"

cd "$work"
npm ci
npm run frontend

mkdir -p "$repo_root/$out/api/server/middleware" \
  "$repo_root/$out/api/app/clients" \
  "$repo_root/$out/packages"

cp librechat.yaml "$repo_root/$out/librechat.yaml"
cp api/server/middleware/canDeleteAccount.js \
  "$repo_root/$out/api/server/middleware/canDeleteAccount.js"
cp api/app/clients/BaseClient.js \
  "$repo_root/$out/api/app/clients/BaseClient.js"
cp -a client/dist "$repo_root/$out/client/dist"
cp -a packages/api/dist "$repo_root/$out/packages/api/dist"
cp -a packages/data-provider/dist "$repo_root/$out/packages/data-provider/dist"
mkdir -p "$repo_root/$out/images"
cp -a images/. "$repo_root/$out/images/" 2>/dev/null || true

echo "LibreChat custom build written to $out"
