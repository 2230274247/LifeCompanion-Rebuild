from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import secrets
import subprocess
from datetime import datetime, timedelta, timezone

import httpx

from .reminders import ReminderPermissionError, ReminderUpstreamError
from .store import utc_now

try:
    from cryptography.fernet import Fernet
except ImportError:  # Windows keeps using DPAPI; Fernet is only required on Linux.
    Fernet = None


def protect(value: dict) -> str:
    """Encrypt per-user reminder credentials with the host's credential store."""
    if os.name == "nt":
        return "d:" + base64.b64encode(_dpapi(json.dumps(value).encode(), False)).decode()
    return "f:" + _fernet().encrypt(json.dumps(value).encode()).decode()


def unprotect(value: str) -> dict:
    if value.startswith("d:"):
        return json.loads(_dpapi(base64.b64decode(value[2:]), True))
    return json.loads(_fernet().decrypt(value[2:].encode()))


def _fernet() -> "Fernet":
    if Fernet is None:
        raise ReminderUpstreamError("CREDENTIAL_VAULT_UNAVAILABLE")
    key = os.getenv("LIFE_CREDENTIAL_MASTER_KEY", "")
    if not key:
        raise ReminderUpstreamError("CREDENTIAL_MASTER_KEY_REQUIRED")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        # Accept a plain passphrase and derive a stable Fernet key from it.
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        return Fernet(derived)


def _dpapi(value: bytes, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise ReminderUpstreamError("CREDENTIAL_VAULT_UNAVAILABLE")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.windll.crypt32
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise ReminderUpstreamError("CREDENTIAL_VAULT_UNAVAILABLE")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


class ReminderProvisioning:
    """Persist a stable identity before upstream calls; recover each Saga step."""

    def __init__(self, store, settings, reminders):
        self.store, self.settings, self.reminders = store, settings, reminders
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reminder_accounts (
                owner_id TEXT PRIMARY KEY, state TEXT NOT NULL, credentials TEXT NOT NULL,
                lease_until TEXT, last_error TEXT, updated_at TEXT NOT NULL
            )""")
            db.execute("CREATE TABLE IF NOT EXISTS reminder_instance (id INTEGER PRIMARY KEY CHECK(id=1), namespace TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO reminder_instance VALUES (1,?)", (secrets.token_hex(8),))
            self.namespace = db.execute("SELECT namespace FROM reminder_instance WHERE id=1").fetchone()[0]

    def row(self, owner):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM reminder_accounts WHERE owner_id=?", (owner,)).fetchone()
        return dict(row) if row else None

    def config(self, owner):
        row = self.row(owner)
        if row:
            config = unprotect(row["credentials"])
            if config.get("api_token") and config.get("project_id"):
                return config
        return self.settings.vikunja_users.get(owner)

    def configs(self):
        result = dict(self.settings.vikunja_users)
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM reminder_accounts WHERE state='ready'").fetchall()
        for row in rows:
            result[row["owner_id"]] = unprotect(row["credentials"])
        return result

    def status(self, owner):
        config = self.config(owner)
        row = self.row(owner)
        if not self.reminders.notifications_allowed(owner):
            state = "consent_required"
        elif row and row["state"] == "provisioning" and row["lease_until"] > utc_now():
            state = "provisioning"
        elif row and row["last_error"]:
            state = "permission_denied" if row["last_error"] == "UPSTREAM_PERMISSION_DENIED" else "service_unavailable"
        elif config:
            state = "ready"
        else:
            state = "not_configured"
        return {"status": state, "configured": bool(config),
                "provisioning_state": row["state"] if row else ("ready" if config else "not_started"),
                "error_code": row["last_error"] if row else None}

    def _save(self, owner, config, state="provisioning", error=None):
        with self.store.connect() as db:
            db.execute("""UPDATE reminder_accounts SET credentials=?,state=?,last_error=?,
                updated_at=?,lease_until=NULL WHERE owner_id=?""",
                       (protect(config), state, error, utc_now(), owner))

    def _api(self, method, path, token=None, **kwargs):
        try:
            response = httpx.request(
                method, self.settings.vikunja_base_url + path,
                headers={"Authorization": f"Bearer {token}"} if token else {},
                timeout=8, **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ReminderUpstreamError("VIKUNJA_UNAVAILABLE") from exc
        if response.is_error:
            code = "UPSTREAM_PERMISSION_DENIED" if response.status_code in (401, 403) else f"VIKUNJA_HTTP_{response.status_code}"
            raise ReminderUpstreamError(code)
        return response.json() if response.content else {}

    def _ntfy(self, *args, password=None):
        # In containers life-core has no Docker socket; use ntfy's admin HTTP API.
        if self.settings.ntfy_admin_user and self.settings.ntfy_admin_password:
            self._ntfy_http(*args, password=password)
            return
        command = ["docker", "exec"]
        if password is not None:
            command += ["-i", self.settings.ntfy_container, "sh", "-c",
                        'read -r NTFY_PASSWORD; export NTFY_PASSWORD; exec ntfy user add "$1"',
                        "--", args[0]]
        else:
            command += [self.settings.ntfy_container, "ntfy", *args]
        try:
            # Binary stdin prevents Windows text mode from adding CR to the Linux password.
            result = subprocess.run(command, input=(password + "\n").encode() if password else None,
                                    capture_output=True, timeout=15,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if password and result.returncode and b"already exists" in result.stderr.lower():
                shell_index = command.index("-c") + 1
                command[shell_index] = command[shell_index].replace("user add", "user change-pass")
                result = subprocess.run(command, input=(password + "\n").encode(),
                                        capture_output=True, timeout=15,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReminderUpstreamError("NTFY_PROVISIONING_UNAVAILABLE") from exc
        if result.returncode:
            raise ReminderUpstreamError("NTFY_PROVISIONING_FAILED")

    def _ntfy_http(self, *args, password=None):
        auth = httpx.BasicAuth(
            self.settings.ntfy_admin_user, self.settings.ntfy_admin_password
        )
        if args and args[0] == "access":
            username, topic, permission = args[1], args[2], args[3]
            self._ntfy_request(
                "PUT", "/v1/users/access", auth,
                json={"username": username, "topic": topic, "permission": permission},
            )
            return
        self._ntfy_request(
            "PUT", "/v1/users", auth,
            json={"username": args[0], "password": password},
        )

    def _ntfy_request(self, method, path, auth, *, json):
        try:
            response = httpx.request(
                method, self.settings.ntfy_base_url + path, auth=auth,
                json=json, timeout=15,
            )
        except httpx.HTTPError as exc:
            raise ReminderUpstreamError("NTFY_PROVISIONING_UNAVAILABLE") from exc
        if response.status_code >= 400:
            raise ReminderUpstreamError(
                f"NTFY_HTTP_{response.status_code}"
                if response.status_code >= 500 else "NTFY_PROVISIONING_FAILED"
            )

    def provision(self, owner, *, renew=False):
        if not renew and not self.reminders.notifications_allowed(owner):
            raise ReminderPermissionError("NOTIFICATION_CONSENT_REQUIRED")
        existing = self.config(owner)
        row = self.row(owner)
        if existing and not renew and (not row or (
            row["state"] == "ready" and existing.get("ntfy_input_version") == 2
        )):
            return self.status(owner)
        now = datetime.now(timezone.utc)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM reminder_accounts WHERE owner_id=?", (owner,)).fetchone()
            if row and row["lease_until"] and row["lease_until"] > now.isoformat():
                return {"status": "provisioning", "configured": bool(existing)}
            if row:
                config = unprotect(row["credentials"])
            else:
                subject = hashlib.sha256(f"{self.namespace}:{owner}".encode()).hexdigest()[:24]
                config = {"username": "lc_" + subject, "password": secrets.token_urlsafe(32),
                          "ntfy_user": "lc_" + subject, "ntfy_password": secrets.token_urlsafe(32),
                          "ntfy_topic": "lc_" + secrets.token_hex(24),
                          "ntfy_base_url": self.settings.ntfy_base_url,
                          "webhook_secret": secrets.token_hex(32)}
                db.execute("INSERT INTO reminder_accounts VALUES (?,?,?,NULL,NULL,?)",
                           (owner, "provisioning", protect(config), utc_now()))
            db.execute("UPDATE reminder_accounts SET state='provisioning',lease_until=?,updated_at=? WHERE owner_id=?",
                       ((now + timedelta(minutes=3)).isoformat(), utc_now(), owner))
        try:
            if not config.get("vikunja_user_id"):
                try:
                    self._api("POST", "/register", json={
                        "username": config["username"], "password": config["password"],
                        "email": config["username"] + "@reminders.invalid"})
                except ReminderUpstreamError as exc:
                    # Register may have succeeded before a crash; only login can recover it.
                    if str(exc) != "VIKUNJA_HTTP_400":
                        raise
            login = self._api("POST", "/login", json={
                "username": config["username"], "password": config["password"]})
            token = login["token"]
            config["vikunja_user_id"] = self._api("GET", "/user", token)["id"]
            if not config.get("project_id"):
                projects = self._api("GET", "/projects", token).get("items", [])
                project = next((p for p in projects if p["title"] == "LifeCompanion Reminders"), None)
                if not project:
                    project = self._api("POST", "/projects", token, json={"title": "LifeCompanion Reminders"})
                config["project_id"] = project["id"]
            if not config.get("webhook_id"):
                target = self.settings.reminder_webhook_url
                hooks = self._api("GET", "/user/settings/webhooks", token).get("items", [])
                hook = next((h for h in hooks if h["target_url"] == target), None)
                if not hook:
                    hook = self._api("POST", "/user/settings/webhooks", token, json={
                        "target_url": target, "events": ["task.reminder.fired"],
                        "secret": config["webhook_secret"]})
                config["webhook_id"] = hook["id"]
            self._ntfy(config["ntfy_user"], password=config["ntfy_password"])
            self._ntfy("access", config["ntfy_user"], config["ntfy_topic"], "rw")
            config["ntfy_input_version"] = 2
            self._rotate(owner, config, token)
            return self.status(owner)
        except (ReminderUpstreamError, KeyError, ValueError) as exc:
            code = str(exc) if isinstance(exc, ReminderUpstreamError) else "UPSTREAM_RESPONSE_INVALID"
            self._save(owner, config, "failed_retryable", code)
            raise ReminderUpstreamError(code) from exc

    def _rotate(self, owner, config, login_token):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        # A lost token response is not readable again: replace only our named tokens.
        old = self._api("GET", "/tokens", login_token).get("items", [])
        created = self._api("POST", "/tokens", login_token, json={
            "title": "LifeCompanion scoped reminders", "expires_at": expires.isoformat(),
            "permissions": {"tasks": ["create", "read_all", "read_one", "update", "delete"],
                            "notifications": ["read_all"]}})
        config.update(api_token=created["token"], token_id=created["id"], token_expires_at=expires.isoformat())
        self._save(owner, config, "ready")
        for item in old:
            if item["title"] == "LifeCompanion scoped reminders" and item["id"] != created["id"]:
                self._api("DELETE", f"/tokens/{item['id']}", login_token)

    def maintain(self):
        with self.store.connect() as db:
            rows = db.execute("SELECT owner_id,credentials FROM reminder_accounts WHERE state='ready'").fetchall()
        for row in rows:
            config = unprotect(row["credentials"])
            if config.get("ntfy_input_version") != 2 or (
                datetime.fromisoformat(config["token_expires_at"]) < datetime.now(timezone.utc) + timedelta(days=1)
            ):
                try:
                    self.provision(row["owner_id"], renew=True)
                except ReminderUpstreamError:
                    continue
