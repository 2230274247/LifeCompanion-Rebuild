"""Run this worktree's life-core against isolated synthetic acceptance storage.

Reads only chat/internal/model credentials from explicitly selected config files.
Memos identities must come from the isolated token map. Models remain offline in
an existing H-drive cache. Existing acceptance SQLite is backed up before startup.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    runtime = root / "infra/runtime/p5"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--embedding-cache", type=Path, required=True)
    parser.add_argument("--tokens-file", type=Path, default=runtime / "memos-tokens.json")
    parser.add_argument("--database-dir", type=Path, default=runtime / "core-data-e2e-chat")
    args = parser.parse_args()
    db_dir = args.database_dir.resolve()
    # This launcher cannot accidentally migrate a production or another worktree's DB.
    if not db_dir.is_relative_to(runtime.resolve()):
        parser.error("database-dir must be inside this worktree's infra/runtime/p5")
    cache = args.embedding_cache.resolve()
    if cache.drive.lower() != "h:" or not cache.is_dir():
        parser.error("embedding-cache must be an existing H-drive model directory")
    tokens = json.loads(args.tokens_file.read_text(encoding="utf-8-sig"))
    if not isinstance(tokens, dict) or not tokens or not all(isinstance(v, str) and v for v in tokens.values()):
        parser.error("isolated Memos token map is empty or invalid")
    selected = {"JWT_SECRET", "JWT_REFRESH_SECRET", "LIFE_INTERNAL_TOKEN", "DEEPSEEK_API_KEY"}
    credentials = {}
    for relative in ("infra/.env", "products/librechat-custom/.env"):
        for line in (args.config_root / relative).read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name in selected:
                credentials[name] = value.strip().strip('"').strip("'")
    if not all(credentials.get(name) for name in selected):
        parser.error("required chat/internal/DeepSeek configuration is missing")
    os.environ.update(credentials)
    db_dir.mkdir(parents=True, exist_ok=True)
    database = db_dir / "life-core.sqlite3"
    if database.exists():
        backup = db_dir / ("prelaunch-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".sqlite3")
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source, sqlite3.connect(backup) as target:
            source.backup(target)
    os.environ.update({
        "LIFE_DATABASE_PATH": str(database),
        "LIFE_MEMOS_TOKENS_FILE": str(args.tokens_file.resolve()),
        "MEMOS_API_TOKEN": next(iter(tokens.values())),
        "MEMOS_BASE_URL": "http://127.0.0.1:15231",
        "LIFE_MEMORY_EMBEDDING_CACHE": str(cache),
        "LIFE_LLM_PROVIDER": "deepseek",
        "LIFE_TIMEZONE": "Asia/Hong_Kong",
        "LIFE_LIBRECHAT_BASE_URL": "http://127.0.0.1:3810",
        "LIFE_ALLOWED_ORIGINS": "http://localhost:3001,http://127.0.0.1:3001",
        "LIFE_VIKUNJA_USERS_FILE": "",
        "IMAGE_PROVIDER_API_KEY": "",
        "SILICONFLOW_API_KEY": "",
        "LIFE_DIRECT_MOMENT_TEST_ENABLED": "false",
    })
    sys.path.insert(0, str(root / "services/life-core"))
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8010)


if __name__ == "__main__":
    main()
