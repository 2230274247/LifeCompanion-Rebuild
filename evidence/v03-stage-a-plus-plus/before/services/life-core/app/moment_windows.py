"""V0.3 business-day windows and their persisted UTC coverage."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


POLICY_VERSION = "v03-a"
DEFAULT_ENDS = ["11:00", "16:00", "24:00"]
LEGACY_ENDS = ["11:00", "17:00", "23:00"]
NIGHT_SETTLE_DELAY = timedelta(minutes=5)


def clock_value(value: str) -> int:
    if value == "24:00":
        return 24 * 60
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def business_bounds(business_date: date, slot: int, timezone_name: str,
                    ends: list[str]) -> tuple[datetime, datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    minutes = [clock_value(value) for value in ends]
    day_start = datetime.combine(business_date, time.min, tzinfo=zone)
    if slot == 0:
        start = day_start
    else:
        start = datetime.combine(
            business_date, time.min, tzinfo=zone
        ) + timedelta(minutes=minutes[slot - 1])
    if slot == 2 and minutes[slot] >= 24 * 60:
        end = datetime.combine(
            business_date + timedelta(days=1), time.min, tzinfo=zone
        )
    else:
        end = datetime.combine(business_date, time.min, tzinfo=zone) + timedelta(
            minutes=minutes[slot]
        )
    settle_after = end + (NIGHT_SETTLE_DELAY if slot == 2 else timedelta())
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc), settle_after.astimezone(timezone.utc)


def next_window_after(
    cursor: datetime,
    now: datetime,
    timezone_name: str,
    ends: list[str],
    used_keys: set[tuple[str, int]],
) -> dict | None:
    """Return the earliest unused business slot whose end is after cursor."""
    local_day = cursor.astimezone(ZoneInfo(timezone_name)).date()
    candidates = []
    for offset in range(-1, 4):
        business_date = local_day + timedelta(days=offset)
        for slot in range(3):
            nominal_start, end, settle_after = business_bounds(
                business_date, slot, timezone_name, ends
            )
            key = (business_date.isoformat(), slot)
            if end <= cursor or key in used_keys:
                continue
            candidates.append({
                "local_date": key[0],
                "slot": slot,
                "timezone": timezone_name,
                "window_start": cursor,
                "window_end": end,
                "settle_after": settle_after,
                "nominal_start": nominal_start,
                "coverage_note": (
                    "POLICY_TRANSITION_CARRY" if cursor > nominal_start else None
                ),
            })
    candidate = min(candidates, key=lambda item: (item["window_end"], item["slot"])) if candidates else None
    if candidate is None or candidate["settle_after"] > now:
        return None
    return candidate


def next_policy_boundary(now: datetime, cursor: datetime, timezone_name: str,
                         ends: list[str]) -> datetime:
    """First unfinished boundary under the currently active policy."""
    local_day = cursor.astimezone(ZoneInfo(timezone_name)).date()
    boundaries = []
    for offset in range(-1, 4):
        business_date = local_day + timedelta(days=offset)
        for slot in range(3):
            _, end, _ = business_bounds(business_date, slot, timezone_name, ends)
            if end > now and end > cursor:
                boundaries.append(end)
    if not boundaries:
        raise ValueError("NEXT_POLICY_BOUNDARY_UNAVAILABLE")
    return min(boundaries)
