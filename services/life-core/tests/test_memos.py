import httpx
import pytest

from app.memos import MemosClient, MemosError


@pytest.mark.parametrize(
    "creator,visibility",
    [("users/other", "PRIVATE"), ("users/a", "PUBLIC")],
)
def test_read_rejects_wrong_owner_or_visibility(monkeypatch, creator, visibility):
    def fake_get(_client, _url, **_kwargs):
        return httpx.Response(200, json={
            "name": "memos/test", "creator": creator, "visibility": visibility, "content": "private",
        })

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    with pytest.raises(MemosError, match="OWNERSHIP"):
        MemosClient("http://memos.invalid", "secret").get_private_memo("memos/test", "users/a")


def test_read_rejects_path_injection():
    with pytest.raises(MemosError, match="INVALID_REFERENCE"):
        MemosClient("http://memos.invalid", "secret").get_private_memo("memos/../../users", "users/a")


def test_wrong_pat_owner_cannot_write_another_users_event(monkeypatch):
    def identity(_client, _url, **_kwargs):
        return httpx.Response(200, json={"user": {"name": "users/admin"}})

    def forbidden_post(*_args, **_kwargs):
        pytest.fail("Memos write must not occur for a mismatched PAT owner")

    monkeypatch.setattr(httpx.Client, "get", identity)
    monkeypatch.setattr(httpx.Client, "post", forbidden_post)
    with pytest.raises(MemosError, match="WRITER_MISMATCH"):
        MemosClient("http://memos.invalid", "secret").create_private_memo({
            "event_id": "evt_test", "title": "test", "summary": "test",
            "source_message_ids": ["one"], "memos_user_id": "users/a",
        })
