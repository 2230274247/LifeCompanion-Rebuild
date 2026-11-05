"""Provision Memos users + PATs for the V0.3 acceptance accounts.

Idempotent: existing PATs are kept, new entries are appended to the shared
tokens file that life-core reloads on startup.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/v03-acceptance"
MEMOS = "http://127.0.0.1:5230"


def env() -> dict:
    data: dict = {}
    for path in (ROOT / "infra/.env", ROOT / "products/librechat-custom/.env"):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                data[key] = value
    return data


def main() -> None:
    config = env()
    admin_token = config["MEMOS_API_TOKEN"]
    tokens_file = Path(config["LIFE_MEMOS_TOKENS_FILE"])
    accounts = json.loads(
        (RUNTIME / "accounts.json").read_text(encoding="utf-8")
    )
    tokens = (
        json.loads(tokens_file.read_text(encoding="utf-8"))
        if tokens_file.exists()
        else {}
    )

    with httpx.Client(timeout=30, trust_env=False) as client:
        for account in accounts.values():
            memos_user_id = f"users/{account['username']}"
            if memos_user_id in tokens:
                continue
            created = client.post(
                f"{MEMOS}/api/users",
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
                raise RuntimeError(
                    f"Memos create {account['username']} HTTP {created.status_code}"
                )
            signin = client.post(
                f"{MEMOS}/api/auth/signin",
                json={
                    "passwordCredentials": {
                        "username": account["username"],
                        "password": account["password"],
                    }
                },
            )
            if signin.status_code != 200:
                raise RuntimeError(
                    f"Memos signin {account['username']} HTTP {signin.status_code}"
                )
            auth = {"Authorization": "Bearer " + signin.json()["accessToken"]}
            pat = client.post(
                f"{MEMOS}/api/{memos_user_id}/personalAccessTokens",
                headers=auth,
                json={
                    "description": "V0.3 acceptance isolated account",
                    "expiresInDays": 7,
                },
            )
            if pat.status_code != 200:
                raise RuntimeError(
                    f"Memos PAT {account['username']} HTTP {pat.status_code}"
                )
            tokens[memos_user_id] = pat.json()["token"]

    tokens_file.parent.mkdir(parents=True, exist_ok=True)
    tokens_file.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    print(f"PASS: {len(tokens)} Memos PAT entries written to {tokens_file}")


if __name__ == "__main__":
    sys.exit(main())
