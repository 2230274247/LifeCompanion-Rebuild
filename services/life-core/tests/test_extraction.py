from datetime import datetime
from zoneinfo import ZoneInfo

from app.extraction import extract_event


NOW = datetime(2026, 11, 2, 18, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))


def test_accepts_real_past_event():
    result = extract_event(
        "今天下午和朋友在公园散步，看见秋天的银杏树，感觉特别放松。",
        now=NOW,
    )
    assert result.accepted is True
    assert result.title == "公园散步"
    assert result.occurred_at.hour == 15
    assert result.confidence >= 0.7


def test_rejects_future_plan():
    result = extract_event("明天下午打算和朋友去公园散步。", now=NOW)
    assert result.accepted is False
    assert result.reason == "future_or_hypothetical"


def test_rejects_negated_event():
    result = extract_event("今天下午没有去公园散步。", now=NOW)
    assert result.accepted is False
    assert result.reason == "negated_event"


def test_rejects_chat_without_event():
    result = extract_event("你好，你最近过得怎么样？", now=NOW)
    assert result.accepted is False

