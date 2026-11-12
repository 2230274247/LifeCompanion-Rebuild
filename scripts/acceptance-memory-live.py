"""Live isolated-account memory acceptance against the real gateway/core/MongoDB.

Registers a throwaway account, bootstraps it into life-core, grants recall
consent, then drives the real save -> cross-window recall -> diagnostics loop
over HTTP. Never prints tokens, secrets or credentials.
"""
import base64
import hashlib
import hmac
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

GATEWAY = "http://127.0.0.1:3001"
CORE = "http://127.0.0.1:8010"
MONGO_CONTAINER = "lifecompanion-mongo"
# Real installation env lives in the main checkout, never in this worktree.
REAL_ROOT = "H:/AI For research institute/LifeCompanion-Rebuild"


def read_env(name):
    for path in (f"{REAL_ROOT}/infra/.env", f"{REAL_ROOT}/products/librechat-custom/.env"):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                for line in handle:
                    line = line.strip()
                    if line.startswith(name + "=") and not line.startswith("#"):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except FileNotFoundError:
            continue
    return ""


INTERNAL = read_env("LIFE_INTERNAL_TOKEN")
JWT_SECRET = read_env("JWT_SECRET")
if not INTERNAL or not JWT_SECRET:
    print("LIVE_FAIL missing internal token or JWT secret")
    sys.exit(1)


def mint(user_id):
    b64 = lambda obj: base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=").decode()
    signing = (f"{b64({'alg': 'HS256', 'typ': 'JWT'})}."
               f"{b64({'id': user_id, 'exp': int(time.time()) + 1800})}")
    sig = base64.urlsafe_b64encode(
        hmac.new(JWT_SECRET.encode(), signing.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{signing}.{sig}"


def request(method, url, body=None, headers=None, timeout=25):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {"_raw": raw[:200].decode("utf-8", "replace")}
        return exc.code, payload


def mongo_user_id(email):
    query = (f"const u=db.getSiblingDB('LibreChat').users.findOne("
             f"{{email:'{email}'}},{{_id:1}}); if(!u){{quit(1)}} print(u._id.toString())")
    out = subprocess.run(
        ["docker", "exec", MONGO_CONTAINER, "mongosh", "--quiet", "--eval", query],
        capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError("mongo lookup failed: " + out.stderr[:200])
    lines = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    return lines[-1]


def main():
    failures = []
    user = "mem-e2e-" + secrets.token_hex(4)
    email = user + "@example.test"
    password = secrets.token_urlsafe(14)

    status, body = request("POST", GATEWAY + "/api/auth/register", {
        "name": "记忆验收", "username": user, "email": email,
        "password": password, "confirm_password": password,
    })
    if status != 200:
        print("LIVE_FAIL register", status)
        return 1

    try:
        uid = mongo_user_id(email)
    except RuntimeError as exc:
        print("LIVE_FAIL", exc)
        return 1

    status, body = request("POST", CORE + "/internal/v1/users/bootstrap", {
        "librechat_user_id": uid, "memos_user_id": f"users/{user}",
        "memos_username": user, "display_name": "记忆验收", "memory_consent": True,
    }, headers={"X-Internal-Token": INTERNAL})
    if status != 200:
        failures.append("bootstrap: %s %s" % (status, str(body)[:120]))

    token = mint(uid)
    status, _ = request("PATCH", CORE + "/api/v1/me/settings",
                        {"recall_consent": True, "sensitive_consent": True},
                        headers={"Authorization": f"Bearer {token}"})
    if status != 200:
        failures.append("grant recall consent: %s" % status)

    # Save a preference in window A through the real enqueue path.
    status, body = request("POST", CORE + "/internal/v1/events/enqueue", {
        "source_user_id": uid, "source_message_id": "live-a",
        "conversation_id": "chat-a", "text": "我最喜欢喝龙井茶",
        "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }, headers={"X-Internal-Token": INTERNAL})
    if status != 200 or not body.get("accepted"):
        failures.append("enqueue: %s %s" % (status, str(body)[:120]))

    # Wait for the background worker to persist the fact.
    saved = False
    for _ in range(20):
        time.sleep(1)
        status, diag = request("GET", CORE + "/api/v1/memory-status",
                               headers={"Authorization": f"Bearer {token}"})
        if status == 200 and any(t.get("status") == "saved" for t in diag.get("traces", [])):
            saved = True
            break
    if not saved:
        failures.append("worker did not persist fact (traces=%s)" % str(diag.get("traces", []))[:200])

    # Cross-window paraphrase recall.
    status, recalled = request("POST", CORE + "/internal/v1/knowledge/recall", {
        "source_user_id": uid, "query": "我以前说过我喜欢喝什么？",
        "conversation_id": "chat-b", "source_message_id": "live-b",
    }, headers={"X-Internal-Token": INTERNAL})
    if status != 200:
        failures.append("recall http: %s" % status)
    elif not any("龙井" in (i.get("text", "") + i.get("canonical_text", ""))
                 for i in (*recalled.get("items", []), *recalled.get("profile", []))):
        failures.append("cross-window recall missed: %s" % str(recalled)[:200])

    # Diagnostics show saved + matched stages.
    status, diag = request("GET", CORE + "/api/v1/memory-status",
                           headers={"Authorization": f"Bearer {token}"})
    statuses = {(t.get("stage"), t.get("status")) for t in diag.get("traces", [])}
    if ("extraction", "saved") not in statuses:
        failures.append("missing saved trace: %s" % statuses)
    if ("recall", "matched") not in statuses:
        failures.append("missing matched trace: %s" % statuses)

    if failures:
        print("LIVE_FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("LIVE_PASS real save, cross-window recall, and diagnostics (isolated account)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
