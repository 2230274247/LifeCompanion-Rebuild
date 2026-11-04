"""Isolated acceptance services; never rewrites production config or its database."""
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/v023"
RUNTIME.mkdir(exist_ok=True)


def environment():
    for path in (ROOT / "infra/.env", ROOT / "products/librechat-custom/.env"):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key] = value
    sys.path.insert(0, str(ROOT / "services/life-core"))


def launch(args, name, cwd=ROOT):
    subprocess.Popen(args, cwd=cwd, stdout=(RUNTIME / (name + ".out.log")).open("ab"),
                     stderr=(RUNTIME / (name + ".err.log")).open("ab"),
                     creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "core":
        environment()
        import uvicorn
        from app.config import load_settings
        from app.main import create_app
        config = replace(load_settings(), database_path=RUNTIME / "life-core.sqlite3",
                         vikunja_users={}, memos_user_tokens=json.loads(
                             (RUNTIME / "memos-tokens.json").read_text()) if (RUNTIME / "memos-tokens.json").exists() else {},
                         librechat_base_url="http://127.0.0.1:3083",
                         reminder_webhook_url="http://host.docker.internal:8023/api/v1/webhooks/vikunja")
        uvicorn.run(create_app(config), host="127.0.0.1", port=8023)
    elif mode == "start":
        raw = subprocess.check_output(["docker", "inspect", "lifecompanion-librechat"])
        container = json.loads(raw)[0]
        values = dict(value.split("=", 1) for value in container["Config"]["Env"])
        values["LIFE_CORE_URL"] = "http://host.docker.internal:8023"
        values["MONGO_URI"] = values["MONGO_URI"].rsplit("/", 1)[0] + "/LibreChatV023"
        # Dedicated synthetic app data; uploads and logs never touch real user directories.
        for key in ("MEILI_HOST", "MEILI_MASTER_KEY"):
            values.pop(key, None)
        values["SEARCH"] = "false"
        envfile = RUNTIME / "librechat.env"
        envfile.write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf8")
        network = next(iter(container["NetworkSettings"]["Networks"]))
        args = ["docker", "run", "-d", "--name", "lifecompanion-v023",
                "--network", network, "-p", "127.0.0.1:3083:3080", "--env-file", str(envfile)]
        for mount in container["Mounts"]:
            destination = mount["Destination"]
            if destination == "/app/.env":
                continue
            source = mount["Source"]
            if destination in ("/app/uploads", "/app/logs"):
                source = str(RUNTIME / destination.rsplit("/", 1)[-1])
                Path(source).mkdir(exist_ok=True)
                args += ["-v", f"{source}:{destination}"]
            else:
                args += ["-v", f"{source}:{destination}:ro"]
        args += [container["Config"]["Image"]]
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit("ISOLATED_CONTAINER_START_FAILED")
        launch([sys.executable, str(Path(__file__).resolve()), "core"], "core")
        launch(["node", "--input-type=module", "-e",
                "import {createGateway} from './apps/product-portal/server.mjs'; "
                "createGateway({chatTarget:'http://127.0.0.1:3083',lifeTarget:'http://127.0.0.1:8023'}).listen(3023,'127.0.0.1');"], "gateway")
        print("Started isolated app :3023, LibreChat :3083, life-core :8023, database LibreChatV023.")
