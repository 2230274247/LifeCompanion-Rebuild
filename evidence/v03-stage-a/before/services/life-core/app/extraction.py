from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ExtractionResult:
    accepted: bool
    reason: str
    title: str | None = None
    summary: str | None = None
    confidence: float = 0.0
    occurred_at: datetime | None = None


_FUTURE_OR_HYPOTHETICAL = (
    "明天",
    "后天",
    "下周",
    "下个月",
    "明年",
    "以后",
    "下次",
    "计划",
    "打算",
    "准备去",
    "想要去",
    "希望",
    "如果",
    "可能会",
    "也许",
    "要去",
    "会去",
    "将去",
)
_NEGATION = ("没有去", "没去", "没有看到", "没看到", "并未", "并不是", "并没有", "没能", "未能")
_PURE_QUESTION = ("为什么", "怎么", "是否", "能不能", "可以吗", "要不要", "什么是")
_EVENT_MARKERS = (
    "去了",
    "到了",
    "散步",
    "看到",
    "看见",
    "遇见",
    "见到",
    "吃了",
    "喝了",
    "聊天",
    "拜访",
    "旅行",
    "拍照",
    "做饭",
    "读书",
    "运动",
    "买了",
    "收到",
    "逛了",
    "公园",
    "朋友",
    "结束了",
    "完成了",
    "结项了",
    "毕业了",
    "获奖了",
    "通过了",
)
_SCENE_PATTERN = re.compile(
    r"(?:在|去)(?P<place>[^，。！？,.!?]{1,20}?)"
    r"(?P<action>散步|走路|看|坐|玩|聊|吃|喝|逛|锻炼|拍照|旅行)"
)


def _event_time(text: str, now: datetime) -> datetime:
    local = now.astimezone(ZoneInfo(now.tzinfo.key if hasattr(now.tzinfo, "key") else "Asia/Hong_Kong"))
    day = local
    if "前天" in text:
        day = local - timedelta(days=2)
    elif "昨天" in text:
        day = local - timedelta(days=1)
    elif "今天" not in text and "今日" not in text:
        day = local

    hour = day.hour
    if "上午" in text or "早上" in text:
        hour = 9
    elif "中午" in text:
        hour = 12
    elif "下午" in text:
        hour = 15
    elif "晚上" in text or "今晚" in text:
        hour = 20
    return day.replace(hour=hour, minute=0, second=0, microsecond=0)


def _title_for(text: str) -> str:
    match = _SCENE_PATTERN.search(text)
    if match:
        place = match.group("place").strip()
        action = match.group("action")
        if action == "走路":
            action = "散步"
        title = f"{place}{action}"
    else:
        title = re.split(r"[，。！？,.!?]", text, maxsplit=1)[0].strip()
    return title[:28] or "生活片段"


def extract_event(text: str, *, now: datetime | None = None, timezone: str = "Asia/Hong_Kong") -> ExtractionResult:
    clean = " ".join(text.split()).strip()
    tz = ZoneInfo(timezone)
    current = (now or datetime.now(tz)).astimezone(tz)

    if len(clean) < 8:
        return ExtractionResult(False, "too_short")
    if any(marker in clean for marker in _FUTURE_OR_HYPOTHETICAL):
        return ExtractionResult(False, "future_or_hypothetical")
    if any(marker in clean for marker in _NEGATION):
        return ExtractionResult(False, "negated_event")
    if clean.startswith(_PURE_QUESTION) or (clean.endswith(("？", "?")) and "今天下午" not in clean):
        return ExtractionResult(False, "question_without_confirmed_event")

    hits = [marker for marker in _EVENT_MARKERS if marker in clean]
    if not hits:
        return ExtractionResult(False, "no_past_event_signal")

    confidence = min(0.55 + 0.07 * len(set(hits)), 0.92)
    if "今天" in clean or "昨天" in clean or "前天" in clean:
        confidence = min(confidence + 0.03, 0.95)

    return ExtractionResult(
        True,
        "accepted",
        title=_title_for(clean),
        summary=clean[:500],
        confidence=round(confidence, 2),
        occurred_at=_event_time(clean, current),
    )

