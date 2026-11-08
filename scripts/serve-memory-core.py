"""Run the checked-out core from the workspace without changing directory.

Existing installation configuration is read only when LIFE_CONFIG_ROOT is explicit.
No values are printed. A SQLite online backup precedes any existing DB migration.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, UTC
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--config-root", type=Path, default=root)
parser.add_argument("--database", type=Path)
parser.add_argument("--port", type=int, default=8010)
args = parser.parse_args()
config_root = args.config_root
if args.database:
    os.environ["LIFE_DATABASE_PATH"] = str(args.database)
os.environ["LIFE_PORT"] = str(args.port)
for relative in ("infra/.env", "products/librechat-custom/.env"):
    path = config_root / relative
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.replace("_", "").isalnum() and not key.startswith("#"):
                os.environ.setdefault(key, value.strip().strip('"').strip("'"))
for key in ("LIFE_MEMOS_TOKENS_FILE", "LIFE_VIKUNJA_USERS_FILE"):
    if os.environ.get(key) and not Path(os.environ[key]).is_absolute():
        os.environ[key] = str(config_root / os.environ[key])
path = Path(os.environ.get("LIFE_DATABASE_PATH", root / "services/life-core/data/life-core.sqlite3"))
if path.exists():
    backup_root = root / "infra/runtime/memory-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".sqlite3")
    with sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True) as source, sqlite3.connect(backup) as target:
        source.backup(target)
os.environ["LIFE_DATABASE_PATH"] = str(path)
os.environ.setdefault("LIFE_MEMORY_EMBEDDING_CACHE", str(root / "services/life-core/data/embedding-models"))
sys.path.insert(0, str(root / "services/life-core"))
import uvicorn
uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("LIFE_PORT", "8010")))
