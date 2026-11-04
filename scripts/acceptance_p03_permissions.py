"""Real authenticated ownership denial matrix against synthetic acceptance IDs."""
import json
from datetime import UTC, datetime

import httpx

from acceptance_environment import ROOT
from verify_rebuild_workspace import verify


def main():
    verify(ROOT)
    accounts = json.loads((ROOT / "infra/runtime/p00/accounts.json").read_text(encoding="utf-8"))
    fixture = json.loads((ROOT / "evidence/p03/draft-live.json").read_text(encoding="utf-8"))
    assert fixture["synthetic_account"] is True
    result = {"status": "FAIL", "provider_calls": 0,
              "started_at": datetime.now(UTC).isoformat(), "checks": {}}
    with httpx.Client(timeout=20, trust_env=False) as client:
        def auth(label):
            account = accounts[label]
            response = client.post("http://127.0.0.1:3091/api/auth/login",
                                   json={"email": account["email"], "password": account["password"]})
            response.raise_for_status()
            return {"Authorization": "Bearer " + response.json()["token"]}
        owner, other = auth("a"), auth("b")
        base = "http://127.0.0.1:8031/api/v1"
        reminder = base + "/reminders/" + fixture["reminder_id"]
        draft = base + "/reminder-drafts/" + fixture["draft_id"]
        before = client.get(reminder, headers=owner)
        before.raise_for_status()
        operations = [
            ("reminder_read", "GET", reminder, None, {}),
            ("reminder_update", "PATCH", reminder, {"title": "MUST_NOT_CHANGE_SYNTHETIC_OWNER_TASK"}, {}),
            ("reminder_cancel", "DELETE", reminder, None, {}),
            ("draft_update", "PATCH", draft, {"title": "MUST_NOT_CHANGE_SYNTHETIC_DRAFT"}, {"If-Match": "1"}),
            ("draft_select", "POST", draft + "/select", {"revision": 1, "fields": {"event_time": "10:00"}}, {}),
            ("draft_confirm", "POST", draft + "/confirm", {"revision": 1, "idempotency_key": "forbidden-owner"}, {}),
            ("draft_reconcile", "POST", draft + "/reconcile", None, {}),
            ("draft_cancel", "DELETE", draft, None, {}),
        ]
        try:
            listed = client.get(base + "/reminder-drafts", headers=other,
                                params={"conversation_id": fixture["conversation_id"]})
            assert listed.status_code == 200 and listed.json()["drafts"] == []
            result["checks"]["draft_list"] = {"status": "PASS", "http_status": 200,
                                               "foreign_drafts_returned": 0}
            for label, method, url, body, extra in operations:
                response = client.request(method, url, headers={**other, **extra},
                                          **({"json": body} if body is not None else {}))
                result["checks"][label] = {"http_status": response.status_code}
                assert response.status_code == 404, f"OWNERSHIP_DENIAL_FAILED_{label}"
                result["checks"][label]["status"] = "PASS"
            after = client.get(reminder, headers=owner)
            after.raise_for_status()
            for key in ("reminder_id", "title", "scheduled_at", "status"):
                assert before.json()["reminder"][key] == after.json()["reminder"][key]
            result.update(status="PASS", owner_state_unchanged=True,
                          reminder_id=fixture["reminder_id"], draft_id=fixture["draft_id"])
        finally:
            result["ended_at"] = datetime.now(UTC).isoformat()
            (ROOT / "evidence/p03/permissions-live.json").write_text(
                json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
