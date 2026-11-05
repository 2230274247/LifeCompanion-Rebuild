"""Provision three fresh accounts plus a real published memory for browser E2E.

The browser acceptance drives the full UI loop with D (owner), E (partner) and
F (outsider). This script only creates fixtures; the UI flow happens in the
browser so no mock data is used for the actual acceptance.
"""

from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/v03-browser"
EVIDENCE = ROOT / "evidence/v03-acceptance/browser"
LIFE_DB = ROOT / "services/life-core/data/life-core.sqlite3"
GATEWAY = "http://127.0.0.1:3001"

sys.path.insert(0, str(ROOT / "services/life-core"))


def register(label: str, name: str, username: str) -> dict:
    suffix = secrets.token_hex(4)
    account = {
        "email": f"v03-{label}-{suffix}@example.test",
        "name": name,
        "username": f"{username}-{suffix}",
        "password": secrets.token_urlsafe(24) + "aA1!",
    }
    with httpx.Client(timeout=60, trust_env=False) as client:
        reg = client.post(
            f"{GATEWAY}/api/auth/register",
            json={**account, "confirm_password": account["password"]},
        )
        if reg.status_code != 200:
            raise RuntimeError(f"register {label} HTTP {reg.status_code}: {reg.text[:200]}")
        login = client.post(
            f"{GATEWAY}/api/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
        if login.status_code != 200:
            raise RuntimeError(f"login {label} HTTP {login.status_code}: {login.text[:200]}")
        account["librechat_user_id"] = login.json()["user"]["id"]
        account["token"] = login.json()["token"]
    return account


def bootstrap(account: dict) -> str:
    from app.store import Store

    store = Store(LIFE_DB)
    store.initialize()
    profile = store.bootstrap_user(
        librechat_user_id=account["librechat_user_id"],
        memos_user_id=f"users/{account['username']}",
        memos_username=account["username"],
        display_name=account["name"],
        memory_consent=True,
        image_consent=True,
    )
    return profile["life_user_id"]


def seed_memory(owner_life_id: str, account: dict) -> dict:
    from app.store import Store

    store = Store(LIFE_DB)
    store.initialize()
    return store.create_event(
        user_id=owner_life_id,
        source_type="chat",
        source_message_ids=["v03-browser-source"],
        conversation_id="v03-browser-conversation",
        occurred_at="2026-11-03T18:30:00+08:00",
        title="一起看晚霞",
        summary="傍晚在江边一起散步看到的晚霞，只在 D 的私有数据中保存。",
        confidence=0.96,
        consent_state="granted",
        status="published",
        idempotency_key=f"v03-browser:{owner_life_id}:sunset",
    )


def load_env() -> dict:
    env: dict = {}
    for path in (ROOT / "infra/.env", ROOT / "products/librechat-custom/.env"):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key] = value
    return env


def provision_memos(accounts: dict) -> None:
    config = load_env()
    admin_token = config["MEMOS_API_TOKEN"]
    tokens_file = Path(config["LIFE_MEMOS_TOKENS_FILE"])
    tokens = (
        json.loads(tokens_file.read_text(encoding="utf-8"))
        if tokens_file.exists()
        else {}
    )
    memos = "http://127.0.0.1:5230"
    changed = False
    with httpx.Client(timeout=30, trust_env=False) as client:
        for account in accounts.values():
            memos_user_id = f"users/{account['username']}"
            if memos_user_id in tokens:
                continue
            created = client.post(
                f"{memos}/api/users",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "username": account["username"],
                    "password": account["password"],
                    "displayName": account["name"],
                    "role": "USER",
                    "state": "NORMAL",
                },
            )
            if created.status_code not in (200, 409):
                raise RuntimeError(f"Memos create HTTP {created.status_code}")
            signin = client.post(
                f"{memos}/api/auth/signin",
                json={
                    "passwordCredentials": {
                        "username": account["username"],
                        "password": account["password"],
                    }
                },
            )
            if signin.status_code != 200:
                raise RuntimeError(f"Memos signin HTTP {signin.status_code}")
            auth = {"Authorization": "Bearer " + signin.json()["accessToken"]}
            pat = client.post(
                f"{memos}/api/{memos_user_id}/personalAccessTokens",
                headers=auth,
                json={
                    "description": "V0.3 browser acceptance isolated account",
                    "expiresInDays": 7,
                },
            )
            if pat.status_code != 200:
                raise RuntimeError(f"Memos PAT HTTP {pat.status_code}")
            tokens[memos_user_id] = pat.json()["token"]
            changed = True
    if changed:
        tokens_file.parent.mkdir(parents=True, exist_ok=True)
        tokens_file.write_text(json.dumps(tokens, indent=2), encoding="utf-8")


def publish(event_id: str, token: str) -> None:
    response = httpx.post(
        "http://127.0.0.1:8010/api/v1/memories/publish",
        headers={"Authorization": f"Bearer {token}"},
        json={"event_id": event_id},
        timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(f"publish HTTP {response.status_code}: {response.text[:200]}")


def reset_collaboration(ids: dict) -> None:
    """Clear only the three synthetic browser-fixture users' collab state."""
    import sqlite3

    user_ids = (ids["d_user_id"], ids["e_user_id"], ids["f_user_id"])
    db = sqlite3.connect(LIFE_DB)
    db.row_factory = sqlite3.Row
    ph = ",".join("?" for _ in user_ids)

    space_ids = [
        r["space_id"]
        for r in db.execute(
            f"""SELECT s.space_id FROM collab_spaces s
                LEFT JOIN collab_space_members m ON m.space_id=s.space_id
                WHERE s.owner_user_id IN ({ph}) OR m.user_id IN ({ph})""",
            (*user_ids, *user_ids),
        ).fetchall()
    ]
    shared_ids = [
        r["shared_memory_id"]
        for r in db.execute(
            f"""SELECT s.shared_memory_id FROM collab_shared_memories s
                LEFT JOIN collab_shared_memory_members m ON m.shared_memory_id=s.shared_memory_id
                WHERE s.created_by IN ({ph}) OR m.user_id IN ({ph})""",
            (*user_ids, *user_ids),
        ).fetchall()
    ]

    for space_id in space_ids:
        db.execute("DELETE FROM collab_space_members WHERE space_id=?", (space_id,))
        db.execute("DELETE FROM collab_space_invites WHERE space_id=?", (space_id,))
        db.execute("DELETE FROM collab_messages WHERE space_id=?", (space_id,))
        db.execute("DELETE FROM collab_spaces WHERE space_id=?", (space_id,))
    for shared_id in shared_ids:
        for table in (
            "collab_shared_memory_members",
            "collab_shared_memory_sources",
            "collab_shared_contributions",
            "collab_shared_messages",
        ):
            db.execute(f"DELETE FROM {table} WHERE shared_memory_id=?", (shared_id,))
        db.execute("DELETE FROM collab_shared_reactions WHERE message_id IN "
                   "(SELECT message_id FROM collab_shared_messages WHERE shared_memory_id=?)",
                   (shared_id,))
        db.execute("DELETE FROM collab_shared_memories WHERE shared_memory_id=?", (shared_id,))

    for table, cols in {
        "collab_shared_memory_invites": ("owner_user_id", "invited_user_id"),
        "collab_shared_memory_join_invites": ("invited_by", "invited_user_id"),
    }.items():
        for col in cols:
            db.execute(f"DELETE FROM {table} WHERE {col} IN ({ph})", user_ids)

    for table, cols in {
        "collab_friend_edges": ("user_low", "user_high"),
        "collab_friend_requests": ("from_user_id", "to_user_id"),
        "collab_blocks": ("blocker_id", "blocked_id"),
        "collab_grants": ("owner_user_id", "grantee_id"),
        "collab_grant_requests": ("requester_id", "owner_user_id"),
        "collab_availability": ("owner_user_id",),
        "collab_statuses": ("owner_user_id",),
        "collab_notifications": ("user_id",),
        "collab_audit": ("actor_user_id",),
        "collab_agent_runs": ("actor_user_id",),
        "collab_events": ("actor_user_id",),
        "collab_reactions": ("user_id",),
        "collab_shared_reactions": ("user_id",),
        "collab_messages": ("sender_id",),
        "collab_shared_messages": ("sender_id",),
    }.items():
        for col in cols:
            db.execute(f"DELETE FROM {table} WHERE {col} IN ({ph})", user_ids)
    db.commit()
    print("reset ok")


def main() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    if "--provision-memos" in sys.argv:
        accounts = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
        provision_memos(accounts)
        print(json.dumps({"status": "memos provisioned"}, ensure_ascii=False))
        return

    if "--reset" in sys.argv:
        ids = json.loads((RUNTIME / "ids.json").read_text(encoding="utf-8"))
        reset_collaboration(ids)
        return

    if "--seed-publish" in sys.argv:
        accounts = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
        ids = json.loads((RUNTIME / "ids.json").read_text(encoding="utf-8"))
        memory = seed_memory(ids["d_user_id"], accounts["d"])
        ids["memory_event_id"] = memory["event_id"]
        (RUNTIME / "ids.json").write_text(
            json.dumps(ids, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        login = httpx.post(
            f"{GATEWAY}/api/auth/login",
            json={"email": accounts["d"]["email"], "password": accounts["d"]["password"]},
            timeout=60,
        )
        if login.status_code == 429:
            raise RuntimeError("login rate limited; restart librechat first")
        login.raise_for_status()
        publish(memory["event_id"], login.json()["token"])
        print(json.dumps({"status": "published", "memory_event_id": memory["event_id"]}, ensure_ascii=False))
        return

    accounts = {
        "d": register("d", "拾光验收·阿琳", "v03-browser-d"),
        "e": register("e", "拾光验收·奶奶", "v03-browser-e"),
        "f": register("f", "拾光验收·路人", "v03-browser-f"),
    }
    for account in accounts.values():
        account["life_user_id"] = bootstrap(account)

    memory = seed_memory(accounts["d"]["life_user_id"], accounts["d"])
    provision_memos(accounts)

    (RUNTIME / "accounts.json").write_text(
        json.dumps(
            {
                "d": {key: accounts["d"][key] for key in
                      ("email", "name", "username", "password", "librechat_user_id")},
                "e": {key: accounts["e"][key] for key in
                      ("email", "name", "username", "password", "librechat_user_id")},
                "f": {key: accounts["f"][key] for key in
                      ("email", "name", "username", "password", "librechat_user_id")},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (RUNTIME / "ids.json").write_text(
        json.dumps(
            {
                "d_user_id": accounts["d"]["life_user_id"],
                "e_user_id": accounts["e"]["life_user_id"],
                "f_user_id": accounts["f"]["life_user_id"],
                "memory_event_id": memory["event_id"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"status": "ok", "memory_event_id": memory["event_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
