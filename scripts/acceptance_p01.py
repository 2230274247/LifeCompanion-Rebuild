"""P01 identity/ownership checks against the isolated, authenticated services."""
import json
import sys
import time
from pathlib import Path

import httpx

from acceptance_p00 import login, check, RUNTIME, ROOT
from verify_rebuild_workspace import verify

verify(ROOT)
OUT = ROOT / "evidence/p01"
OUT.mkdir(parents=True, exist_ok=True)

def wait_ready():
    for attempt in range(40):
        try:
            if httpx.get("http://127.0.0.1:3091/health", timeout=2,
                         trust_env=False).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    raise RuntimeError("ISOLATED_CHAT_NOT_READY")


def prepare():
    wait_ready()
    client, _ = login("a")
    check(client.patch("/life-api/api/v1/me/settings", json={
        "notification_consent": True,
    }), "SYNTHETIC_NOTIFICATION_CONSENT")
    result = check(client.post("/life-api/api/v1/reminder-provisioning"),
                   "ISOLATED_REMINDER_PROVISIONING")
    report = {"status": result.json().get("status"), "synthetic_account_only": True,
              "image_consent": False}
    (OUT / "reminder-provisioning.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


def verify_identities():
    wait_ready()
    client, _ = login("a")
    baseline = json.loads((RUNTIME / "baseline-state.json").read_text(encoding="utf-8"))
    links = check(client.get("/life-api/api/v1/chat-links",
                           params={"conversation_id": baseline["c"]["conversation_id"]}), "LINKS").json()
    ids = [item["memory_id"] for item in links["links"]]
    reminders = check(client.get("/life-api/api/v1/reminders"), "REMINDERS").json()["reminders"]
    reminder_ids = [item["reminder_id"] for item in reminders]
    tests = []
    for label in "bcdefgh":
        other, _ = login(label)
        identity = check(other.get("/life-api/api/v1/me"), "ME").json()
        denied = [other.get("/life-api/api/v1/knowledge/" + identifier).status_code
                  for identifier in ids]
        reminder_denied = [
            other.get("/life-api/api/v1/reminders/" + identifier).status_code
            for identifier in reminder_ids
        ]
        tests.append({"account": label, "identity_mapped": bool(identity["life_user_id"]),
                      "knowledge_denials": denied, "reminder_denials": reminder_denied,
                      "pass": all(code == 404 for code in denied + reminder_denied)})
        other.close()
    check(client.get("/life-api/api/v1/me"), "ME")
    previous = client.headers["Authorization"]
    client.headers["Authorization"] = "Bearer invalid-token"
    expired = client.get("/life-api/api/v1/me").status_code
    client.headers["Authorization"] = previous
    report = {"checks": tests, "malformed_auth_denied_http": expired,
              "pass": bool(ids and reminder_ids) and all(t["pass"] for t in tests) and expired == 401}
    (OUT / "identity-e2e.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    {"prepare": prepare, "identities": verify_identities}[sys.argv[1]]()
