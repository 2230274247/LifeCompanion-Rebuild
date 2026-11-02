from __future__ import annotations

import uuid
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
                raise MemosError(f"MEMOS_CREATE_FAILED:{response.status_code}:{response.text[:300]}")
            return self._memo_name(response)

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

