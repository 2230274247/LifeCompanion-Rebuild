"""Launch only the isolated Rebuild stack with fresh application credentials."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from verify_rebuild_workspace import CANONICAL_ROOT, ROOT, verify

verify(ROOT)
RUNTIME = ROOT / "infra/runtime/p00"
RUNTIME.mkdir(parents=True, exist_ok=True)
ENVFILE = RUNTIME / "acceptance.env"
PYTHON = ROOT / "infra/runtime/p02/venv/Scripts/python.exe"


def dotenv(path):
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8-sig").splitlines()
                if "=" in line and not line.lstrip().startswith("#"))


def prepare():
    if ENVFILE.exists():
        return
    original = dotenv(CANONICAL_ROOT / "products/librechat-custom/.env")
    keys = ("ZHIPU_API_KEY", "ZHIPU_BASE_URL", "ZHIPU_MODEL", "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "LIFE_LLM_PROVIDER",
            "MEMORY_LLM_MODEL", "MEMORY_LLM_URL", "MEMORY_LLM_MAX_TOKENS")
    env = {k: original[k] for k in keys if original.get(k)}
    env.update({
        "JWT_SECRET": secrets.token_hex(32), "JWT_REFRESH_SECRET": secrets.token_hex(32),
        "CREDS_KEY": secrets.token_hex(32), "CREDS_IV": secrets.token_hex(16),
        "LIFE_INTERNAL_TOKEN": secrets.token_hex(32),
        "ACCEPTANCE_VIKUNJA_SECRET": secrets.token_hex(32),
        "LIFE_DATABASE_PATH": str(RUNTIME / "life-core.sqlite3"),
        "MEMOS_BASE_URL": "http://127.0.0.1:5241",
        "LIFE_LIBRECHAT_BASE_URL": "http://127.0.0.1:3091",
        "LIFE_VIKUNJA_BASE_URL": "http://127.0.0.1:3461/api/v2",
        "LIFE_NTFY_BASE_URL": "http://127.0.0.1:8097",
        "LIFE_NTFY_CONTAINER": "lcr-acceptance-20261103-ntfy-1",
        "LIFE_REMINDER_WEBHOOK_URL": "http://host.docker.internal:8031/api/v1/webhooks/vikunja",
        "LIFE_REMINDER_SCHEDULER_DB": str(RUNTIME / "reminder-scheduler.sqlite3"),
        "LIFE_ALLOWED_ORIGINS": "http://127.0.0.1:3031",
        "LIFE_MEMOS_TOKENS_FILE": str(RUNTIME / "memos-tokens.json"),
        "LIFE_TIMEZONE": "Asia/Hong_Kong",
        "SCHEDULES_SINGLE_PROCESS": "true",
        "DEBUG_LOGGING": "false", "DEBUG_CONSOLE": "false",
    })
    ENVFILE.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n", encoding="utf-8")
    (RUNTIME / "memos-tokens.json").write_text("{}", encoding="utf-8")


def environment():
    os.environ.update(dotenv(ENVFILE))
    neo4j_env = RUNTIME.parent / "p02" / "neo4j.env"
    if neo4j_env.exists():
        graph = dotenv(neo4j_env)
        os.environ["LIFE_NEO4J_URI"] = "bolt://127.0.0.1:7688"
        os.environ["LIFE_NEO4J_USER"] = "neo4j"
        os.environ["LIFE_NEO4J_PASSWORD"] = graph["NEO4J_AUTH"].split("/", 1)[1]
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(ROOT / "services/life-core"))


def launch(args, name):
    process = subprocess.Popen(
        args, cwd=ROOT,
        stdout=(RUNTIME / f"{name}.out.log").open("ab"),
        stderr=(RUNTIME / f"{name}.err.log").open("ab"),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    (RUNTIME / f"{name}.pid").write_text(str(process.pid), encoding="ascii")
    return process.pid


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "prepare":
        prepare()
        print("Prepared isolated secrets and provider configuration; no values printed.")
    elif mode == "core":
        environment()
        import uvicorn
        from app.main import create_app
        uvicorn.run(create_app(), host="127.0.0.1", port=8031)
    elif mode == "services":
        environment()
        pids = {
            "core": launch([str(PYTHON), str(Path(__file__).resolve()), "core"], "core"),
            "gateway": launch(["node", "--input-type=module", "-e",
                "import {createGateway} from './apps/product-portal/server.mjs'; "
                "createGateway({chatTarget:'http://127.0.0.1:3091',"
                "lifeTarget:'http://127.0.0.1:8031'}).listen(3031,'127.0.0.1');"], "gateway"),
        }
        print(json.dumps({"pids": pids, "gateway": "http://127.0.0.1:3031"}))
    elif mode == "core-service":
        environment()
        pid = launch([str(PYTHON), str(Path(__file__).resolve()), "core"], "core")
        print(json.dumps({"core_pid": pid}))
