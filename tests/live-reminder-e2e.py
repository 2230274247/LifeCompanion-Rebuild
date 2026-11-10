"""真实提醒端到端验收：life-core → 真实 Vikunja 任务 → 真实 webhook → 真实 ntfy 通知。

隔离性：复用隔离合成账号（spa-a）与其独立 ntfy topic，但为本测试单独铸一个
短期 Vikunja API token，并注册指向 8011 的独立 webhook，绝不改写主工作树 users.json、
也不触碰主 life-core（8010）的既有 webhook。独立 sqlite；不改动真实业务数据。
本脚本只读 gitignored 上游凭据（默认取本仓库 `infra/runtime/reminders/`，可用
环境变量 `LIFE_CREDS_ROOT` 指向产品基线工作树），不打印、不提交任何秘密。

前置：本机 Vikunja(:3456) 与 ntfy(:8087) 已运行；`infra/runtime/reminders/users.json`
与 `spa-accounts.json` 内存在 vikunja_user_id==2 的 spa-a 合成账号。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CREDS_ROOT = Path(os.environ.get("LIFE_CREDS_ROOT", ROOT))
RUNTIME = ROOT / "infra" / "runtime" / "reminder-live"
RUNTIME.mkdir(exist_ok=True, parents=True)

VIKUNJA_API = "http://127.0.0.1:3456/api/v1"
VIKUNJA_V2 = "http://127.0.0.1:3456/api/v2"
PORT = 8011
WEBHOOK_TARGET = f"http://host.docker.internal:{PORT}/api/v1/webhooks/vikunja"
LIBRECHAT_ID = "spa-a-reminder-live"
LIFE_ID = "life_" + hashlib.sha256(LIBRECHAT_ID.encode()).hexdigest()[:20]
RUN_ID = datetime.now(timezone.utc).astimezone().strftime("%H%M%S%f")
REMINDER_TITLE = f"拾光真实联网提醒验收-{RUN_ID}"

result = {
    "started_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "life_user_id": LIFE_ID,
    "checks": {},
    "status": "FAIL",
}

_proc = None


def vik(method: str, path: str, **kw):
    r = requests.request(method, VIKUNJA_API + path, timeout=10, **kw)
    r.raise_for_status()
    return r


def mint_api_token(username: str, password: str) -> tuple[str, str]:
    """用 spa-a 登录名密码登录，返回 (scoped_api_token, session_token)。

    webhook 管理需用 session_token（登录 JWT），任务/通知操作才用 scoped api_token。
    """
    login = requests.post(
        VIKUNJA_API + "/login", json={"username": username, "password": password}, timeout=10
    )
    login.raise_for_status()
    session_token = login.json()["token"]
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    created = requests.post(
        VIKUNJA_V2 + "/tokens",
        headers={"Authorization": "Bearer " + session_token},
        json={
            "title": "Life-core reminder-live e2e",
            "expires_at": expires.isoformat(),
            "permissions": {
                "tasks": ["create", "read_all", "read_one", "update", "delete"],
                "notifications": ["read_all"],
            },
        },
        timeout=10,
    )
    created.raise_for_status()
    return created.json()["token"], session_token


def ensure_webhook(session_token: str, secret: str) -> int:
    """为 8011 注册独立 webhook（不动 8010 主链路既有 webhook），返回 id。

    用登录 JWT 管理 webhook（scoped api_token 无此权限）。
    """
    auth = {"Authorization": "Bearer " + session_token}
    hooks = vik("GET", "/user/settings/webhooks", headers=auth).json()
    existing = next((w for w in hooks if w.get("target_url") == WEBHOOK_TARGET), None)
    if existing is not None:
        return existing["id"]
    created = vik(
        "PUT",
        "/user/settings/webhooks",
        json={"target_url": WEBHOOK_TARGET, "events": ["task.reminder.fired"], "secret": secret},
        headers=auth,
    ).json()
    return created["id"]


def main() -> None:
    # 1. 载入隔离账号 spa-a（vikunja_user_id == 2）及其登录凭据
    users = json.loads((CREDS_ROOT / "infra/runtime/reminders/users.json").read_text(encoding="utf-8"))
    config = next(v for v in users.values() if v.get("vikunja_user_id") == 2)
    accounts = json.loads((CREDS_ROOT / "infra/runtime/reminders/spa-accounts.json").read_text(encoding="utf-8"))
    login = next(v for v in accounts.values() if str(v.get("vikunja_user_id")) == "2")

    # 2. 铸新 token + 注册 8011 独立 webhook（旧 token 已过期，须用登录名密码）
    config["api_token"], session_token = mint_api_token(login["username"], login["password"])
    auth = {"Authorization": "Bearer " + config["api_token"]}
    webhook_id = ensure_webhook(session_token, config["webhook_secret"])
    result["checks"]["webhook_registered"] = f"PASS id={webhook_id} -> {WEBHOOK_TARGET}"

    # 3. 写隔离 vikunja_users 映射文件（携带新 token）
    mapping = {LIFE_ID: config}
    mapping_file = RUNTIME / "vikunja-users.json"
    mapping_file.write_text(json.dumps(mapping), encoding="utf-8")

    # 4. 启动带提醒配置的 life-core（独立 sqlite + 独立端口，每次全新隔离库）
    db_path = RUNTIME / "life-core.sqlite3"
    if db_path.exists():
        db_path.unlink()
    env = os.environ.copy()
    env.update({
        "LIFE_VIKUNJA_BASE_URL": VIKUNJA_V2,
        "LIFE_VIKUNJA_USERS_FILE": str(mapping_file),
        "LIFE_DATABASE_PATH": str(db_path),
        "LIFE_PORT": str(PORT),
        "LIFE_HOST": "127.0.0.1",
        "LIFE_TIMEZONE": "Asia/Hong_Kong",
        "LIFE_MEMOS_TOKENS_FILE": str(RUNTIME / "memos-empty.json"),
        "LIFE_INTERNAL_TOKEN": "reminder-live-internal-token",
        "JWT_SECRET": "reminder-live-jwt-secret",
        "JWT_REFRESH_SECRET": "reminder-live-refresh-secret",
    })
    (RUNTIME / "memos-empty.json").write_text("{}", encoding="utf-8")
    env["PYTHONPATH"] = str(ROOT / "services" / "life-core")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT / "services" / "life-core"),
        env=env,
        stdout=(RUNTIME / "core.out.log").open("ab"),
        stderr=(RUNTIME / "core.err.log").open("ab"),
    )
    global _proc
    _proc = proc
    result["core_pid"] = proc.pid

    base = f"http://127.0.0.1:{PORT}"
    internal = {"X-Internal-Token": "reminder-live-internal-token"}
    ready = False
    for _ in range(60):
        try:
            if requests.get(base + "/docs", timeout=1).status_code == 200:
                ready = True
                break
        except requests.RequestException:
            time.sleep(0.5)
    if not ready:
        result["checks"]["core_ready"] = "FAIL"
        _finish()
        return
    result["checks"]["core_ready"] = "PASS"

    # 5. bootstrap 用户 + 开通知权限
    r = requests.post(base + "/internal/v1/users/bootstrap", headers=internal, json={
        "librechat_user_id": LIBRECHAT_ID, "memos_user_id": "users/spa-a-reminder",
    }, timeout=10)
    r.raise_for_status()
    user = r.json()
    result["checks"]["bootstrap_life_id_matches"] = "PASS" if user["life_user_id"] == LIFE_ID else "FAIL"
    r = requests.patch(base + "/api/v1/me/settings", headers={
        "Authorization": "Bearer " + _token(LIBRECHAT_ID),
    }, json={"notification_consent": True}, timeout=10)
    r.raise_for_status()

    # 6. 创建真实提醒（约 75 秒后触发，向上取整到分钟）
    fire_at = datetime.now(timezone.utc) + timedelta(seconds=75)
    r = requests.post(base + "/api/v1/reminders", headers={
        "Authorization": "Bearer " + _token(LIBRECHAT_ID),
    }, json={
        "title": REMINDER_TITLE,
        "scheduled_at": fire_at.isoformat(),
        "timezone": "Asia/Hong_Kong",
        "delivery_channel": "push",
    }, timeout=15)
    if r.status_code != 200:
        result["checks"]["create_reminder"] = f"FAIL {r.status_code} {r.text[:200]}"
        _finish()
        return
    reminder = r.json()["reminder"]
    result["reminder"] = {k: reminder.get(k) for k in ("reminder_id", "title", "scheduled_at", "status", "upstream_task_id")}
    result["checks"]["create_reminder"] = "PASS"

    # 7. 验证真实 Vikunja 任务存在（公开 API 不含 upstream_task_id，按标题查 project 内任务）
    tasks = vik("GET", f"/projects/{config['project_id']}/tasks", headers=auth).json()
    items = tasks if isinstance(tasks, list) else tasks.get("items", [])
    match = next((t for t in items if t.get("title") == reminder["title"]), None)
    result["checks"]["real_vikunja_task"] = "PASS" if match else "FAIL"
    if match:
        result["upstream_task_id"] = match.get("id")

    # 8. 等真实触发 -> webhook -> ntfy
    deadline = time.monotonic() + 200
    delivered = False
    while time.monotonic() < deadline:
        time.sleep(5)
        try:
            r = requests.get(
                f"{config['ntfy_base_url'].rstrip('/')}/{config['ntfy_topic']}/json",
                params={"poll": "1", "since": "10m"},
                auth=(config["ntfy_user"], config["ntfy_password"]),
                timeout=8,
            )
            r.raise_for_status()
            for line in r.text.splitlines():
                if line:
                    msg = json.loads(line)
                    if msg.get("title") == "Shiguang" and RUN_ID in msg.get("message", ""):
                        delivered = True
                        result["ntfy_notification"] = {"id": msg.get("id"), "time": msg.get("time")}
        except requests.RequestException:
            continue
        if delivered:
            break
    result["checks"]["ntfy_delivered"] = "PASS" if delivered else "FAIL"

    # 9. 校验本地状态已 fired（store 用 'due' 表示已触发，'completed' 表示已完成）
    r = requests.get(base + "/api/v1/reminders", headers={"Authorization": "Bearer " + _token(LIBRECHAT_ID)}, timeout=10)
    rows = r.json().get("reminders", []) if r.status_code == 200 else []
    result["checks"]["local_fired"] = "PASS" if any(x.get("status") in ("due", "completed") for x in rows) else "FAIL"

    _finish()


def _token(user_id: str) -> str:
    import base64
    import hmac
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"id": user_id, "exp": int(time.time()) + 3600}
    enc = lambda v: base64.urlsafe_b64encode(json.dumps(v, separators=(",", ":")).encode()).rstrip(b"=")
    parts = [enc(header), enc(payload)]
    signature = hmac.new(b"reminder-live-jwt-secret", b".".join(parts), hashlib.sha256).digest()
    parts.append(base64.urlsafe_b64encode(signature).rstrip(b"="))
    return b".".join(parts).decode()


def _finish():
    global _proc
    if _proc is not None:
        try:
            _proc.terminate()
            _proc.wait(timeout=5)
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
        _proc = None
    result["finished_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    ok = bool(result["checks"]) and not result.get("exception") and all(
        isinstance(v, str) and v.startswith("PASS") for v in result["checks"].values()
    )
    result["status"] = "PASS" if ok else "FAIL"
    (RUNTIME / "real-reminder-e2e-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        result["exception"] = f"{type(exc).__name__}: {exc}"
        _finish()
