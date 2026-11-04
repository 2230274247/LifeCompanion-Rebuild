"""Provision one isolated synthetic LibreChat/Memos/Core account without printing secrets."""

from __future__ import annotations

import argparse
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]


def env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("'\"")
    return values


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def require(response: httpx.Response, code: str) -> dict:
    if response.status_code not in (200, 201):
        raise RuntimeError(f"{code}:HTTP_{response.status_code}")
    try:
        value = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{code}:INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{code}:INVALID_RESPONSE")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--chat-url", default="http://127.0.0.1:3092")
    parser.add_argument("--memos-url", default="http://127.0.0.1:5241")
    parser.add_argument("--core-url")
    parser.add_argument("--account-suffix", default="")
    parser.add_argument("--account-key", default="owner")
    parser.add_argument("--email")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--name")
    parser.add_argument("--all-consents", action="store_true")
    parser.add_argument(
        "--acceptance-env",
        default=str(ROOT / "infra/runtime/p00/acceptance.env"),
    )
    parser.add_argument(
        "--main-env",
        default="H:/AI For research institute/LifeCompanion-Rebuild/infra/.env",
    )
    args = parser.parse_args()

    runtime = Path(args.runtime_dir).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    accounts_path = runtime / "accounts.json"
    tokens_path = runtime / "memos-tokens.json"
    env = env_file(Path(args.main_env))
    acceptance_env = env_file(Path(args.acceptance_env))
    admin_token = env.get("MEMOS_API_TOKEN", "").strip()
    if not admin_token:
        raise RuntimeError("MEMOS_ADMIN_TOKEN_NOT_CONFIGURED")

    accounts = (
        json.loads(accounts_path.read_text(encoding="utf-8"))
        if accounts_path.exists()
        else {}
    )
    account = accounts.setdefault(
        args.account_key,
        {
            "email": (
                args.email or
                "v03-b2-e2e-owner@example.invalid"
                if not args.account_suffix
                else f"v03-b2-e2e-{args.account_suffix}@example.invalid"
            ),
            "username": (
                args.username or
                "v03-b2-e2e-owner"
                if not args.account_suffix
                else f"v03-b2-e2e-{args.account_suffix}"
            ),
            "name": (
                args.name or
                "V0.3 B2 合成链路用户"
                if not args.account_suffix
                else f"V0.3 B2 合成链路用户 {args.account_suffix}"
            ),
            "password": args.password or secrets.token_urlsafe(30) + "aA1!",
        },
    )
    write_json(accounts_path, accounts)

    with httpx.Client(timeout=30, trust_env=False) as client:
        if not account.get("librechat_user_id"):
            response = client.post(
                args.chat_url.rstrip("/") + "/api/auth/register",
                json={
                    "email": account["email"],
                    "username": account["username"],
                    "name": account["name"],
                    "password": account["password"],
                    "confirm_password": account["password"],
                },
            )
            require(response, "LIBRECHAT_REGISTER_FAILED")
            write_json(accounts_path, accounts)
        login = client.post(
            args.chat_url.rstrip("/") + "/api/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
        login_body = require(login, "LIBRECHAT_LOGIN_FAILED")
        account["librechat_user_id"] = login_body.get("user", {}).get("id")
        if not account["librechat_user_id"]:
            raise RuntimeError("LIBRECHAT_USER_ID_MISSING")
        write_json(accounts_path, accounts)

        if not account.get("memos_user_id"):
            memos_create = client.post(
                args.memos_url.rstrip("/") + "/api/users",
                headers={"Authorization": "Bearer " + admin_token},
                json={
                    "username": account["username"],
                    "password": account["password"],
                    "displayName": account["name"],
                    "role": "USER",
                    "state": "NORMAL",
                },
            )
            body = require(memos_create, "MEMOS_USER_CREATE_FAILED")
            account["memos_user_id"] = body.get("name")
            if not account["memos_user_id"]:
                raise RuntimeError("MEMOS_USER_ID_MISSING")
            write_json(accounts_path, accounts)

        memos_login = client.post(
            args.memos_url.rstrip("/") + "/api/auth/signin",
            json={
                "passwordCredentials": {
                    "username": account["username"],
                    "password": account["password"],
                }
            },
        )
        memos_login_body = require(memos_login, "MEMOS_LOGIN_FAILED")
        access_token = memos_login_body.get("accessToken")
        if not access_token:
            raise RuntimeError("MEMOS_ACCESS_TOKEN_MISSING")
        tokens = (
            json.loads(tokens_path.read_text(encoding="utf-8"))
            if tokens_path.exists()
            else {}
        )
        if not tokens.get(account["memos_user_id"]):
            pat = client.post(
                f"{args.memos_url.rstrip('/')}/api/{account['memos_user_id']}/personalAccessTokens",
                headers={"Authorization": "Bearer " + access_token},
                json={"description": "V0.3 B2 isolated E2E", "expiresInDays": 1},
            )
            pat_body = require(pat, "MEMOS_PAT_CREATE_FAILED")
            token = pat_body.get("token")
            if not token:
                raise RuntimeError("MEMOS_PAT_MISSING")
            tokens[account["memos_user_id"]] = token
        write_json(tokens_path, tokens)

        if args.core_url:
            core = client.post(
                args.core_url.rstrip("/") + "/internal/v1/users/bootstrap",
                headers={
                    "X-Internal-Token": acceptance_env.get("LIFE_INTERNAL_TOKEN", "")
                },
                json={
                    "librechat_user_id": account["librechat_user_id"],
                    "memos_user_id": account["memos_user_id"],
                    "memos_username": account["username"],
                    "display_name": account["name"],
                    "memory_consent": bool(args.all_consents),
                    "image_consent": bool(args.all_consents),
                },
            )
            require(core, "CORE_BOOTSTRAP_FAILED")
            if args.all_consents:
                token = login_body.get("token")
                if not token:
                    raise RuntimeError("LIBRECHAT_ACCESS_TOKEN_MISSING")
                life_headers = {"Authorization": "Bearer " + token}
                settings = client.patch(
                    args.core_url.rstrip("/") + "/api/v1/me/settings",
                    headers=life_headers,
                    json={
                        "memory_consent": True,
                        "image_consent": True,
                        "recall_consent": True,
                        "sensitive_consent": True,
                        "notification_consent": True,
                    },
                )
                require(settings, "CORE_PERMISSIONS_FAILED")
                moments = client.put(
                    args.core_url.rstrip("/") + "/api/v1/moment-settings",
                    headers=life_headers,
                    json={
                        "enabled": True,
                        "timezone": "Asia/Hong_Kong",
                        "ends": ["11:00", "16:00", "24:00"],
                    },
                )
                require(moments, "CORE_MOMENT_SETTINGS_FAILED")
                for purpose, provider_name in (
                    ("semantic_scoring", "deepseek"),
                    ("prompt_generation", "deepseek"),
                    ("image_generation", "kolors"),
                ):
                    consent = client.put(
                        args.core_url.rstrip("/")
                        + "/api/v1/moment-egress-consents/"
                        + purpose,
                        headers=life_headers,
                        json={
                            "provider": provider_name,
                            "granted": True,
                            "consent_version": "recollection-egress-v1",
                        },
                    )
                    require(consent, f"CORE_{purpose.upper()}_CONSENT_FAILED")

    result = {
        "status": "PASS",
        "classification": "SYNTHETIC_ISOLATED_ACCOUNT",
        "created_at": datetime.now(UTC).isoformat(),
        "email": account["email"],
        "librechat_user_id": account["librechat_user_id"],
        "memos_user_id": account["memos_user_id"],
        "core_bootstrap": "DONE" if args.core_url else "PENDING",
        "all_consents": bool(args.all_consents),
        "credentials_printed": False,
    }
    write_json(runtime / "bootstrap-result.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
