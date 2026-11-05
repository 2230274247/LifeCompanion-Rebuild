from datetime import datetime, timezone

import httpx

from app.reminder_parser import parse, choices


def test_saved_account_timezone_is_used_without_china_location(tmp_path):
    from test_api import bootstrap, make_app
    from test_memory_pipeline import auth
    app,client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        response = client.patch("/api/v1/me/settings",headers=auth(),json={"timezone":"America/New_York"})
        assert response.status_code == 200
        assert client.get("/api/v1/me",headers=auth()).json()["timezone"] == "America/New_York"
        draft = app.state.reminder_drafts.create(user["life_user_id"],"new-york-chat","new-york-message","明天早上提醒我带雨伞。")
        assert draft["timezone"] == "America/New_York"
        assert draft["missing_fields"] == ["event_time"]
        assert client.patch("/api/v1/me/settings",headers=auth(),json={"timezone":"1"}).status_code == 422
from app.reminder_drafts import preview
from test_api import make_app, token_for

NOW = datetime(2026, 11, 3, 1, tzinfo=timezone.utc)


def test_a_only_clock_missing_and_constraints_preserved():
    text = "明天早上提醒我带绿色 U 盘，不是银色的。"
    fields = parse(text, "Asia/Shanghai", NOW)
    assert fields["event_date"] == "2026-11-04"
    assert fields["title"] == "带绿色 U 盘，不是银色的"
    assert preview(fields, NOW)[0] == ["event_time"]
    assert [i["value"] for i in choices(fields, ["event_time"], text)["options"]] == ["08:00", "09:00", "10:00"]


def test_b_separate_event_and_notification_clocks():
    fields = parse("明天下午 3 点在 1101 开会，明天早上 9 点提醒我。", "Asia/Shanghai", NOW)
    value = preview(fields, NOW)[1]
    assert value["event_at"] == "2026-11-04T15:00:00+08:00"
    assert value["scheduled_at"] == "2026-11-04T09:00:00+08:00"


def test_c_date_not_inferred_from_arrival_and_d_no_fabricated_clock():
    fields = parse("到杭州后晚上 5 点在中国计量大学开会，提前 2 小时提醒我。", "Asia/Shanghai", NOW)
    assert preview(fields, NOW)[0] == ["event_date"]
    fields["event_date"] = "2026-11-04"
    assert preview(fields, NOW)[1]["scheduled_at"] == "2026-11-04T15:00:00+08:00"
    assert parse("明天出门记得带雨伞。", "Asia/Shanghai", NOW)["event_time"] is None


def test_server_clock_respects_user_zone_across_midnight():
    fields = parse("明天9点提醒我带U盘", "America/New_York", NOW)
    assert fields["event_date"] == "2026-11-03"
    fields = parse("明天9点提醒我带U盘", "Asia/Shanghai", NOW)
    assert fields["event_date"] == "2026-11-04"


def test_quick_selection_creates_once_real_adapter_and_cancel_updates_draft(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    a = {"Authorization": "Bearer " + token_for("v023-a")}
    b = {"Authorization": "Bearer " + token_for("v023-b")}
    tasks = []

    def upstream(method, url, **kwargs):
        if method == "POST":
            tasks.append({"id": 9301, **kwargs["json"]})
            return httpx.Response(200, json=tasks[-1])
        if method == "DELETE":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"items": tasks})

    monkeypatch.setattr("app.reminders.httpx.request", upstream)
    text = "明天早上提醒我带绿色 U 盘，不是银色的。"
    monkeypatch.setattr("app.main.httpx.get", lambda *_a, **_k: httpx.Response(
        200, json=[{"messageId": "source", "isCreatedByUser": True, "text": text}]))
    with client:
        owner = client.get("/api/v1/me", headers=a).json()["life_user_id"]
        client.get("/api/v1/me", headers=b)
        app.state.settings.vikunja_users[owner] = {"api_token": "synthetic", "project_id": 1, "vikunja_user_id": 1}
        client.patch("/api/v1/me/settings", headers=a, json={"notification_consent": True})
        draft = app.state.reminder_drafts.create(owner, "conversation", "source", text)
        path = "/api/v1/reminder-drafts/" + draft["draft_id"]
        body = {"revision": 1, "fields": {"event_time": "09:00"}}
        assert client.post(path + "/select", headers=b, json=body).status_code == 404
        result = client.post(path + "/select", headers=a, json=body)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "scheduled"
        reminder_id = result.json()["reminder"]["reminder_id"]
        assert client.post(path + "/select", headers=a, json=body).json()["status"] == "scheduled"
        assert len(tasks) == 1
        detail = client.get("/api/v1/reminders/" + reminder_id, headers=a).json()
        assert detail["reminder"]["source"]["source_message_id"] == "source"
        assert client.get("/api/v1/reminders/" + reminder_id, headers=b).status_code == 404
        assert client.delete(path, headers=a).json()["status"] == "cancelled"
        assert app.state.store.get_reminder(reminder_id, owner)["status"] == "cancelled"
