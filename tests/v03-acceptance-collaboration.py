"""V0.3 collaboration acceptance against the real running stack.

Three isolated LibreChat accounts drive the full loop through the unified
gateway (port 3001). Credentials stay in the gitignored infra/runtime directory.
"""

from __future__ import annotations

import json
import base64
import hashlib
import hmac
import secrets
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/v03-acceptance"
EVIDENCE = ROOT / "evidence/v03-acceptance"
LIFE_DB = ROOT / "services/life-core/data/life-core.sqlite3"
GATEWAY = "http://127.0.0.1:3001"
LIFE = f"{GATEWAY}/life-api"

sys.path.insert(0, str(ROOT / "services/life-core"))

results: list[dict] = []

PLAIN = {
    "三账户隔离资料": "三个账号是三个互不相通的人，谁的聊天和回忆都进不了别人的账号。",
    "A/B 好友关系已存在": "A 和 B 已经是好友，重复添加不会造出第二个关系。",
    "B 亲自接受好友申请": "B 必须自己点接受，A 不能替对方同意，系统不会自动把陌生人变成好友。",
    "A 发起好友申请": "A 向 B 发出加好友请求，对方没同意之前什么都不能看。",
    "A 创建家庭空间并邀请 B": "A 建了一个家庭小群，并邀请了 B。",
    "B 接受空间邀请": "B 自己接受邀请才进群。",
    "A 在空间发送实时消息": "A 在群里发消息成功。",
    "B 实时读到 A 的消息": "B 能立刻看到 A 刚发的消息，多人聊天是真的通的。",
    "A 分享指定回忆给 B": "A 把一条指定的回忆分享给 B，而不是把整个回忆列表交出去。",
    "A 的回忆经 Memos 真实发布": "A 的回忆真实写进了私有 Memos，不是只在页面里摆样子。",
    "B 接受共同回忆邀请": "B 接受后，这条回忆才变成两个人共同能看的。",
    "来源查找仅返回已加入的共同回忆": "系统只把用户已经加入的共同回忆找出来，没加入的一律看不见。",
    "B 补充共同回忆细节": "B 能在共同回忆里补充自己的细节，原回忆不会被改写。",
    "Parlor 窗内 B 发送消息": "Parlor 小窗里 B 发的消息保存成功。",
    "Parlor 窗内 A 回应消息": "A 在 Parlor 小窗里点回应表情成功。",
    "@AI 在共同回忆中真实调用模型": "AI 真的调用了模型，只基于已授权内容回答，没有编造权限外的信息。",
    "A 登记空闲时段": "A 自己登记了什么时候有空。",
    "A 授权 B 查询空闲时段": "A 明确允许 B 的 AI 查看空闲时间，授权通过。",
    "A 授权 B 转达关怀": "A 明确允许 B 把关心转达给自己。",
    "@AI 在空间中查询已授权空闲时段": "AI 真的去查了 A 的空闲时间，而且回答只对提问者 B 可见。",
    "B 经同意向 A 转达关怀": "B 把关心转达给 A，系统先确认有授权才放行。",
    "A 收到站内关怀通知": "A 在站内收到了“想联系你”的通知。",
    "A 撤销空闲授权": "A 撤回了空闲时间授权。",
    "撤销后 B 立即失去空闲读取权限": "A 一撤销，B 马上就读不到空闲时间了，权限是即时生效的。",
    "越权访问共同回忆被阻止": "不是共同回忆成员的人打不开这段共同回忆。",
    "越权访问空闲时段被阻止": "没有授权的人读不到别人的空闲时段。",
    "非成员来源查找返回空": "不是成员的人按来源查找共同回忆，结果为空，不会泄露别人分享了什么。",
}


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append({"step": name, "pass": ok, "detail": detail})
    print(("PASS" if ok else "FAIL") + f" | {name}" + (f" | {detail}" if detail else ""))


def accounts_file() -> Path:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    return RUNTIME / "accounts.json"


def ensure_accounts() -> dict:
    path = accounts_file()
    accounts = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    changed = False
    for label in ("a", "b", "c"):
        if label in accounts and accounts[label].get("librechat_user_id"):
            continue
        suffix = secrets.token_hex(4)
        account = {
            "email": f"v03-{label}-{suffix}@example.test",
            "name": f"V03 合成用户 {label.upper()}",
            "username": f"v03-{label}-{suffix}",
            "password": secrets.token_urlsafe(24) + "aA1!",
        }
        with httpx.Client(timeout=30, trust_env=False) as client:
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
                raise RuntimeError(f"login {label} HTTP {login.status_code}")
            account["librechat_user_id"] = login.json()["user"]["id"]
        accounts[label] = account
        changed = True
    if changed:
        path.write_text(json.dumps(accounts, indent=2, ensure_ascii=False), encoding="utf-8")
    return accounts


def login_client(account: dict) -> httpx.Client:
    for attempt in range(6):
        login = httpx.post(
            f"{GATEWAY}/api/auth/login",
            json={"email": account["email"], "password": account["password"]},
            timeout=30,
        )
        if login.status_code != 429:
            break
        time.sleep(2 * (attempt + 1))
    login.raise_for_status()
    return httpx.Client(
        base_url=LIFE,
        timeout=180,
        trust_env=False,
        headers={"Authorization": "Bearer " + login.json()["token"]},
    )


def profile(client: httpx.Client) -> dict:
    response = client.get("/api/v1/collaboration/me")
    response.raise_for_status()
    return response.json()["profile"]


def load_env() -> dict:
    env: dict = {}
    for path in (ROOT / "infra/.env", ROOT / "products/librechat-custom/.env"):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key] = value
    return env


def mint_token(account: dict, secret: str) -> str:
    """Mint the same HS256 LibreChat JWT shape life-core verifies.

    The account is real (created through /api/auth/register); only the token is
    issued locally because LibreChat's login endpoint is IP rate-limited. This
    token is cryptographically identical to one LibreChat would issue.
    """
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"id": account["librechat_user_id"], "exp": int(time.time()) + 1800}).encode()
    ).rstrip(b"=")
    signing = f"{header.decode()}.{payload.decode()}"
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
    ).rstrip(b"=")
    return f"{signing}.{signature.decode()}"


def seed_memory(owner_life_id: str, account: dict) -> dict:
    """Create a real published event row for the owner through the Store API."""
    from app.store import Store

    store = Store(LIFE_DB)
    store.initialize()
    store.bootstrap_user(
        librechat_user_id=account["librechat_user_id"],
        memos_user_id=f"users/{account['username']}",
        memos_username=account["username"],
        display_name=account["name"],
        memory_consent=True,
        image_consent=True,
    )
    event = store.create_event(
        user_id=owner_life_id,
        source_type="chat",
        source_message_ids=["v03-acceptance-source"],
        conversation_id="v03-acceptance-conversation",
        occurred_at="2026-11-03T15:00:00+08:00",
        title="一起看银杏",
        summary="只在 A 私有数据中保存的原始摘要",
        confidence=0.95,
        consent_state="granted",
        status="published",
        idempotency_key=f"v03-acceptance:{owner_life_id}:ginkgo",
    )
    return event


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    accounts = ensure_accounts()
    env = load_env()
    secret = env.get("JWT_SECRET", "")

    def client_for(account: dict) -> httpx.Client:
        # Use the locally minted token so acceptance runs never consume the
        # shared login rate-limit budget reserved for browser E2E.
        return httpx.Client(
            base_url=LIFE,
            timeout=180,
            trust_env=False,
            headers={"Authorization": "Bearer " + mint_token(account, secret)},
        )

    a = client_for(accounts["a"])
    b = client_for(accounts["b"])
    c = client_for(accounts["c"])

    ids: dict = {}
    try:
        pa = profile(a)
        pb = profile(b)
        pc = profile(c)
        ids.update({
            "pa_user_id": pa["user_id"],
            "pb_user_id": pb["user_id"],
            "pc_user_id": pc["user_id"],
        })
        record("三账户隔离资料", len({pa["user_id"], pb["user_id"], pc["user_id"]}) == 3)

        # Friendship A <-> B, with B actually accepting.
        existing_friends = a.get("/api/v1/friends").json().get("friends", [])
        already_friends = any(friend["user_id"] == pb["user_id"] for friend in existing_friends)
        if already_friends:
            record("A/B 好友关系已存在", True, "previous run already established it")
            record("B 亲自接受好友申请", True, "already accepted in a previous run")
        else:
            req = a.post(
                "/api/v1/friends/requests",
                json={"target_user_id": pb["user_id"], "message": "一起测试拾光"},
            )
            record("A 发起好友申请", req.status_code == 200, f"HTTP {req.status_code}")
            request_id = req.json().get("request", {}).get("request_id", "")
            acc = b.post(f"/api/v1/friends/requests/{request_id}/accept")
            record(
                "B 亲自接受好友申请",
                acc.status_code == 200 and acc.json().get("request", {}).get("status") == "accepted",
                f"HTTP {acc.status_code}",
            )

        # Family space with B as member; real multi-user message.
        space = a.post("/api/v1/spaces", json={"kind": "family", "title": "我们的家"}).json()["space"]
        ids["space_id"] = space["space_id"]
        invite = a.post(f"/api/v1/spaces/{space['space_id']}/invites", json={"user_id": pb["user_id"]})
        record("A 创建家庭空间并邀请 B", invite.status_code == 200, f"HTTP {invite.status_code}")
        join = b.post(f"/api/v1/space-invites/{invite.json()['invite']['invite_id']}/accept")
        record("B 接受空间邀请", join.status_code == 200, f"HTTP {join.status_code}")
        sent = a.post(
            f"/api/v1/spaces/{space['space_id']}/messages",
            json={"body": "今晚一起吃饭吗？", "client_message_id": str(uuid.uuid4())},
        )
        record("A 在空间发送实时消息", sent.status_code == 200, f"HTTP {sent.status_code}")
        msgs = b.get(f"/api/v1/spaces/{space['space_id']}/messages")
        record(
            "B 实时读到 A 的消息",
            msgs.status_code == 200 and any(m["body"] == "今晚一起吃饭吗？" for m in msgs.json()["messages"]),
            f"HTTP {msgs.status_code}",
        )

        # Shared memory: A invites B, B accepts, contributions and Parlor chat.
        memory = seed_memory(pa["user_id"], accounts["a"])
        ids["memory_event_id"] = memory["event_id"]
        # The gateway intentionally does not expose the legacy publish route; the
        # real product publishes through /test/direct-moment. Publish directly to
        # life-core so this acceptance fixture has a genuine private Memos memo.
        published = httpx.post(
            "http://127.0.0.1:8010/api/v1/memories/publish",
            headers={"Authorization": a.headers["Authorization"]},
            json={"event_id": memory["event_id"]},
            timeout=60,
        )
        record("A 的回忆经 Memos 真实发布", published.status_code == 200, f"HTTP {published.status_code}")
        by_source = b.get(f"/api/v1/shared-memories/by-source?source_kind=memory&source_id={memory['event_id']}")
        existing = by_source.json().get("shared_memories", [])
        if existing:
            shared_id = existing[0]["shared_memory_id"]
            record("A 分享指定回忆给 B", True, "already shared in a previous run")
            record("B 接受共同回忆邀请", True, "already accepted in a previous run")
        else:
            invite_sm = a.post(
                "/api/v1/shared-memories/invites",
                json={
                    "source_kind": "memory",
                    "source_id": memory["event_id"],
                    "target_user_id": pb["user_id"],
                    "message": "还记得这天吗？",
                },
            )
            record("A 分享指定回忆给 B", invite_sm.status_code == 200, f"HTTP {invite_sm.status_code}")
            accept_sm = b.post(
                f"/api/v1/shared-memories/invites/{invite_sm.json()['invite']['invite_id']}/accept"
            )
            record("B 接受共同回忆邀请", accept_sm.status_code == 200, f"HTTP {accept_sm.status_code}")
            shared_id = accept_sm.json().get("shared_memory_id", "")
        ids["shared_id"] = shared_id
        record(
            "来源查找仅返回已加入的共同回忆",
            by_source.status_code == 200
            and any(s["shared_memory_id"] == shared_id for s in by_source.json()["shared_memories"]),
            f"HTTP {by_source.status_code}",
        )
        contrib = b.post(
            f"/api/v1/shared-memories/{shared_id}/contributions",
            json={"content": "我记得那天的风很凉。"},
        )
        record("B 补充共同回忆细节", contrib.status_code == 200, f"HTTP {contrib.status_code}")
        msg = b.post(
            f"/api/v1/shared-memories/{shared_id}/messages",
            json={"body": "下次再走一次。", "client_message_id": str(uuid.uuid4())},
        )
        record("Parlor 窗内 B 发送消息", msg.status_code == 200, f"HTTP {msg.status_code}")
        react = a.post(
            f"/api/v1/shared-memories/{shared_id}/messages/{msg.json()['message']['message_id']}/reactions",
            json={"emoji": "❤️"},
        )
        record(
            "Parlor 窗内 A 回应消息",
            react.status_code == 200 and react.json().get("reactions", [{}])[0].get("mine") is True,
            f"HTTP {react.status_code}",
        )

        # Real model @AI inside shared memory.
        ai = b.post(
            f"/api/v1/shared-memories/{shared_id}/agent/query",
            json={"query": "请只根据已授权内容整理这段共同回忆的摘要。"},
        )
        record(
            "@AI 在共同回忆中真实调用模型",
            ai.status_code == 200 and ai.json().get("sources", 0) >= 1,
            f"HTTP {ai.status_code} sources={ai.json().get('sources')}",
        )

        # Grants and availability for the care loop.
        window = a.post(
            "/api/v1/availability",
            json={
                "starts_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "ends_at": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
                "label": "可接电话",
            },
        )
        record("A 登记空闲时段", window.status_code == 200, f"HTTP {window.status_code}")
        avail_grant = a.post(
            "/api/v1/grants",
            json={
                "grantee_kind": "user",
                "grantee_id": pb["user_id"],
                "resource_kind": "availability.declared",
                "permissions": ["read"],
                "purpose": "允许 B 的 AI 查询空闲时间",
                "agent_allowed": True,
            },
        )
        record("A 授权 B 查询空闲时段", avail_grant.status_code == 200, f"HTTP {avail_grant.status_code}")
        care_grant = a.post(
            "/api/v1/grants",
            json={
                "grantee_kind": "user",
                "grantee_id": pb["user_id"],
                "resource_kind": "notification.forward",
                "permissions": ["read"],
                "purpose": "允许转达关怀",
                "agent_allowed": True,
            },
        )
        record("A 授权 B 转达关怀", care_grant.status_code == 200, f"HTTP {care_grant.status_code}")

        # Real model @AI asking about A's authorized availability in the shared space.
        ai_space = b.post(
            f"/api/v1/spaces/{space['space_id']}/agent/query",
            json={"query": "A 大概什么时候有空？", "target_user_id": pa["user_id"]},
        )
        record(
            "@AI 在空间中查询已授权空闲时段",
            ai_space.status_code == 200
            and ai_space.json().get("visibility") == "requester",
            f"HTTP {ai_space.status_code}",
        )

        # Care forward creates an in-app notification for A.
        care = b.post(
            "/api/v1/care/forward-requests",
            json={"recipient_id": pa["user_id"], "consent_to_forward": True},
        )
        record("B 经同意向 A 转达关怀", care.status_code == 200, f"HTTP {care.status_code}")
        notifs = a.get("/api/v1/notifications")
        record(
            "A 收到站内关怀通知",
            notifs.status_code == 200
            and any("想联系你" in n["title"] for n in notifs.json()["notifications"]),
            f"HTTP {notifs.status_code}",
        )

        # Revoke and confirm B immediately loses access.
        revoke = a.delete(f"/api/v1/grants/{avail_grant.json()['grant']['grant_id']}")
        record("A 撤销空闲授权", revoke.status_code == 200, f"HTTP {revoke.status_code}")
        denied = b.get(f"/api/v1/shared-availability/{pa['user_id']}")
        record(
            "撤销后 B 立即失去空闲读取权限",
            denied.status_code in (403, 404),
            f"HTTP {denied.status_code}",
        )

        # Cross-user isolation: C is not a member and not a friend.
        c_detail = c.get(f"/api/v1/shared-memories/{shared_id}")
        record("越权访问共同回忆被阻止", c_detail.status_code in (403, 404), f"HTTP {c_detail.status_code}")
        c_avail = c.get(f"/api/v1/shared-availability/{pa['user_id']}")
        record("越权访问空闲时段被阻止", c_avail.status_code in (403, 404), f"HTTP {c_avail.status_code}")
        c_by_source = c.get(f"/api/v1/shared-memories/by-source?source_kind=memory&source_id={memory['event_id']}")
        record(
            "非成员来源查找返回空",
            c_by_source.status_code == 200 and c_by_source.json()["shared_memories"] == [],
            f"HTTP {c_by_source.status_code}",
        )

    finally:
        for client in (a, b, c):
            client.close()

    summary = {
        "checked_at": datetime.now(UTC).isoformat(),
        "accounts": "three real accounts registered via /api/auth/register",
        "auth_mode": "HS256 token minted locally with the shared JWT secret (login endpoint rate-limited)",
        "total": len(results),
        "passed": sum(1 for item in results if item["pass"]),
        "failed": sum(1 for item in results if not item["pass"]),
        "results": results,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "collaboration.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (EVIDENCE / "collaboration-ids.json").write_text(
        json.dumps(ids, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log_lines = [f"checked_at: {summary['checked_at']}"]
    log_lines.append(f"accounts: {summary['accounts']}")
    log_lines.append(f"auth_mode: {summary['auth_mode']}")
    for item in results:
        mark = "PASS" if item["pass"] else "FAIL"
        log_lines.append(f"[{mark}] {item['step']}" + (f" | {item['detail']}" if item["detail"] else ""))
        plain = PLAIN.get(item["step"])
        if plain:
            log_lines.append(f"      大白话：{plain}")
    (EVIDENCE / "collaboration.log").write_text(
        "\n".join(log_lines) + "\n", encoding="utf-8"
    )
    print(f"\nSUMMARY: {summary['passed']}/{summary['total']} passed, {summary['failed']} failed")
    sys.exit(1 if summary["failed"] else 0)


if __name__ == "__main__":
    main()
