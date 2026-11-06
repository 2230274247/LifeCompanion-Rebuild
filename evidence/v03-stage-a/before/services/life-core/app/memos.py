from __future__ import annotations

import uuid
import re
from typing import Any

import httpx


class MemosError(RuntimeError):
    pass


class MemosClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def memo_id_for_event(event_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"lifecompanion:{event_id}"))

    @staticmethod
    def render_memo(event: dict[str, Any]) -> str:
        sources = ", ".join(f"`{value}`" for value in event["source_message_ids"])
        return (
            f"# {event['title']}\n\n"
            f"{event['summary']}\n\n"
            f"> AI 生活伙伴记录 · 事件 `{event['event_id']}`\n"
            f"> 来源消息：{sources}\n\n"
            "#生活回忆 #AI生活伙伴"
        )

    def create_private_memo(self, event: dict[str, Any]) -> str:
        if not self.configured:
            raise MemosError("MEMOS_NOT_CONFIGURED")

        memo_id = self.memo_id_for_event(event["event_id"])
        payload = {
            "content": self.render_memo(event),
            "visibility": "PRIVATE",
            "state": "NORMAL",
        }
        timeout = httpx.Timeout(20, connect=5)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            identity = client.get(f"{self.base_url}/api/auth/me", headers=self.headers)
            if not identity.is_success:
                raise MemosError(f"MEMOS_IDENTITY_FAILED:{identity.status_code}")
            try:
                writer = identity.json()["user"]["name"]
            except (ValueError, KeyError, TypeError) as exc:
                raise MemosError("MEMOS_INVALID_IDENTITY") from exc
            if writer != event.get("memos_user_id"):
                raise MemosError("MEMOS_WRITER_MISMATCH")
            response = client.post(
                f"{self.base_url}/api/memos",
                params={"memoId": memo_id},
                headers=self.headers,
                json=payload,
            )
            if response.status_code == 409 or self._already_exists(response):
                existing = client.get(
                    f"{self.base_url}/api/memos/{memo_id}", headers=self.headers
                )
                if existing.is_success:
                    return self._memo_name(existing)
                raise MemosError(f"MEMOS_CONFLICT_WITHOUT_READ:{existing.status_code}")
            if not response.is_success:
                raise MemosError(f"MEMOS_CREATE_FAILED:{response.status_code}")
            return self._memo_name(response)

    def get_private_memo(self, memo_ref: str, expected_creator: str) -> dict[str, Any]:
        if not self.configured:
            raise MemosError("MEMOS_NOT_CONFIGURED")
        if not re.fullmatch(r"memos/[A-Za-z0-9_-]+", memo_ref):
            raise MemosError("MEMOS_INVALID_REFERENCE")
        try:
            with httpx.Client(timeout=httpx.Timeout(10, connect=3), trust_env=False) as client:
                response = client.get(f"{self.base_url}/api/{memo_ref}", headers=self.headers)
            if not response.is_success:
                raise MemosError(f"MEMOS_READ_FAILED:{response.status_code}")
            memo = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MemosError("MEMOS_READ_UNAVAILABLE") from exc
        if not isinstance(memo, dict) or not isinstance(memo.get("content"), str):
            raise MemosError("MEMOS_INVALID_RESPONSE")
        if (
            memo.get("name") != memo_ref
            or memo.get("creator") != expected_creator
            or memo.get("visibility") != "PRIVATE"
            or memo.get("state", "NORMAL") != "NORMAL"
        ):
            raise MemosError("MEMOS_OWNERSHIP_MISMATCH")
        return memo

    def delete_private_memo(self, memo_ref: str, expected_creator: str) -> None:
        try:
            self.get_private_memo(memo_ref, expected_creator)
        except MemosError as exc:
            if str(exc) == "MEMOS_READ_FAILED:404":
                return
            raise
        with httpx.Client(timeout=10, trust_env=False) as client:
            response = client.delete(f"{self.base_url}/api/{memo_ref}", headers=self.headers)
        if not response.is_success and response.status_code != 404:
            raise MemosError("MEMOS_DELETE_FAILED")

    @staticmethod
    def _already_exists(response: httpx.Response) -> bool:
        if "already" not in response.text.lower() and "exist" not in response.text.lower():
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        return payload.get("code") in {6, "6", "ALREADY_EXISTS"}

    @staticmethod
    def _memo_name(response: httpx.Response) -> str:
        payload = response.json()
        name = payload.get("name")
        if not name or not str(name).startswith("memos/"):
            raise MemosError("MEMOS_INVALID_RESPONSE")
        return str(name)

