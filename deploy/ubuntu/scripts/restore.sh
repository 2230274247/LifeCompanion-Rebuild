#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 backups/backup-YYYYMMDD-HHMMSS.tar.gz" >&2
  exit 1
fi

archive="$1"
if [[ ! -f "$archive" ]]; then
  echo "ERROR: backup archive not found: $archive" >&2
  exit 1
fi

work="backups/.restore"
rm -rf "$work"
mkdir -p "$work"
tar -xzf "$archive" -C "$work"

./scripts/stop.sh

if [[ -f "$work/life-core.sqlite3" ]]; then
  mkdir -p volumes/life-core-data
  cp "$work/life-core.sqlite3" volumes/life-core-data/life-core.sqlite3
fi
if [[ -d "$work/mongo" ]]; then
  rm -rf volumes/librechat-mongo
  mkdir -p volumes/librechat-mongo
  cp -a "$work/mongo/." volumes/librechat-mongo/
fi
for archive_file in "$work"/*.tar.gz; do
  [[ -e "$archive_file" ]] || continue
  tar -C volumes -xzf "$archive_file"
done

rm -rf "$work"
./scripts/start.sh
echo "Restore complete. Run ./scripts/healthcheck.sh to verify."
