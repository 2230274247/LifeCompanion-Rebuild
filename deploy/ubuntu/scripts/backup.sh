#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

stamp="$(date +%Y%m%d-%H%M%S)"
out="backups/backup-${stamp}"
mkdir -p "$out"

# Preserve life-core's SQLite store and the Mongo database in one place.
if [[ -f volumes/life-core-data/life-core.sqlite3 ]]; then
  cp volumes/life-core-data/life-core.sqlite3 "$out/life-core.sqlite3"
fi

docker compose exec -T mongo mongodump \
  --db LibreChat --out /data/db/backup 2>/dev/null || true
if [[ -d volumes/librechat-mongo/backup ]]; then
  cp -a volumes/librechat-mongo/backup "$out/mongo"
fi

# Snapshot the remaining bind-mounted volumes (uploads, memos, vikunja, ntfy, meili).
for vol in librechat-uploads librechat-logs memos vikunja vikunja-files ntfy-auth ntfy-cache librechat-meili; do
  if [[ -d "volumes/$vol" ]]; then
    tar -C volumes -czf "$out/${vol}.tar.gz" "$vol"
  fi
done

tar -czf "backups/backup-${stamp}.tar.gz" -C backups "backup-${stamp}"
rm -rf "$out"
echo "Backup written to backups/backup-${stamp}.tar.gz"
