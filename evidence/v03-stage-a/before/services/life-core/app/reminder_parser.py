"""Calendar parsing uses the server clock; quoted user constraints stay intact."""
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NUM = r"(?:\d{1,2}|[一二两三四五六七八九十]{1,3})"
CLOCK = re.compile(rf"(?:(凌晨|早上|上午|中午|下午|晚上|傍晚)\s*)?({NUM})\s*(?:[:：]([0-5]\d)|点(半|[0-5]?\d分?)?)")


def number(value):
    if value.isdigit():
        return int(value)
    digits = dict(zip("一二两三四五六七八九", [1, 2, 2, 3, 4, 5, 6, 7, 8, 9]))
    if "十" in value:
        left, right = value.split("十")
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    return digits[value]


def calendar_day(text, today):
    full = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})", text)
    if full:
        return date(*map(int, full.groups())).isoformat()
    for word, offset in (("后天", 2), ("明天", 1), ("今天", 0)):
        if word in text:
            return (today + timedelta(days=offset)).isoformat()
    return None


def parse(text, zone_name, now=None):
    zone = ZoneInfo(zone_name)
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(zone).date()
    fields = dict(title=None, event_date=calendar_day(text, today), event_time=None,
                  timezone=zone_name, lead_minutes=0, place=None,
                  reminder_date=None, reminder_time=None)
    place = re.search(r"义乌|北京|上海|杭州|广州|深圳|香港", text)
    if place:
        fields["place"] = place[0]
        fields["timezone"] = "Asia/Hong_Kong" if place[0] == "香港" else "Asia/Shanghai"
        today = now.astimezone(ZoneInfo(fields["timezone"])).date()
        fields["event_date"] = calendar_day(text, today)
    # An IANA zone explicitly written by the user wins over the account setting.
    explicit_zone = re.search(r"\b[A-Za-z]+/[A-Za-z_]+(?:/[A-Za-z_]+)?\b", text)
    if explicit_zone:
        ZoneInfo(explicit_zone[0])
        fields["timezone"] = explicit_zone[0]
        today = now.astimezone(ZoneInfo(explicit_zone[0])).date()
        fields["event_date"] = calendar_day(text, today)
    clocks = []
    for match in CLOCK.finditer(text):
        hour = number(match[2])
        if match[1] in ("下午", "晚上", "傍晚") and hour < 12:
            hour += 12
        if match[1] == "中午" and hour < 11:
            hour += 12
        minute = int(match[3]) if match[3] else (30 if match[4] == "半" else int((match[4] or "0").rstrip("分")))
        clocks.append((match, time(hour, minute).isoformat()))
    if clocks:
        fields["event_time"] = clocks[0][1]
    if len(clocks) >= 2:
        match, clock = clocks[-1]
        if re.match(r"\s*提醒", text[match.end():]):
            fields["reminder_time"] = clock
            prefix = text[:match.start()].split("，")[-1].split(",")[-1]
            fields["reminder_date"] = calendar_day(prefix, today) or fields["event_date"]
            fields["event_date"] = calendar_day(text[:clocks[0][0].end()], today)
    lead = re.search(r"提前\s*(\d+|一|两|二|半)\s*(小时|分钟|分)", text)
    if re.search(r"(?:不用|无需|不必|不要)提前", text):
        fields["lead_minutes"] = 0
    elif lead:
        quantity = 0.5 if lead[1] == "半" else number(lead[1])
        fields["lead_minutes"] = int(quantity * (60 if lead[2] == "小时" else 1))
    elif re.search(r"提前|之前|前提醒", text):
        fields["lead_minutes"] = None
    carrying = re.search(r"带(.+)", text)
    if carrying:
        fields["title"] = "带" + carrying[1].strip("。！!?？ ")
    elif re.search(r"高铁|赶车", text):
        fields["title"] = "赶高铁"
    else:
        fields["title"] = text.strip("。！!?？ ")[:200]
    return fields


def choices(fields, missing, text):
    if not fields.get("timezone"):
        return None
    if "event_date" in missing:
        today = datetime.now(ZoneInfo(fields["timezone"])).date()
        return {"field": "event_date", "options": [
            {"label": "今天", "value": today.isoformat()},
            {"label": "明天", "value": (today + timedelta(days=1)).isoformat()}], "other": "date"}
    if "event_time" in missing:
        times = ["08:00", "09:00", "10:00"]
        if re.search("下午|中午", text):
            times = ["13:00", "14:00", "15:00"]
        elif re.search("晚上|傍晚", text):
            times = ["18:00", "19:00", "20:00"]
        return {"field": "event_time", "options": [{"label": t, "value": t} for t in times], "other": "time"}
    return None
