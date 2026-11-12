"""Grounded calendar intervals; message timestamps are anchors, never event defaults."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Occurrence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(default="", max_length=200)
    unit: Literal["unknown", "day", "week", "month", "year"] = "unknown"
    offset: int | None = Field(default=None, ge=-36525, le=36525, strict=True)
    weekday: int | None = Field(default=None, ge=0, le=6, strict=True)
    year: int | None = Field(default=None, ge=1, le=9999, strict=True)
    month: int | None = Field(default=None, ge=1, le=12, strict=True)
    day: int | None = Field(default=None, ge=1, le=31, strict=True)

    @model_validator(mode="after")
    def coherent(self):
        if self.unit == "unknown":
            if any(v is not None for v in (self.offset, self.weekday, self.year, self.month, self.day)):
                raise ValueError("UNKNOWN_OCCURRENCE_HAS_NO_DATE")
            return self
        if not self.expression.strip():
            raise ValueError("OCCURRENCE_EVIDENCE_REQUIRED")
        if self.offset is not None:
            if any(v is not None for v in (self.year, self.month, self.day)):
                raise ValueError("CONFLICTING_OCCURRENCE_ANCHORS")
            if self.weekday is not None and self.unit != "week":
                raise ValueError("WEEKDAY_REQUIRES_WEEK")
        else:
            if self.year is None or self.weekday is not None or self.unit == "week":
                raise ValueError("ABSOLUTE_OCCURRENCE_REQUIRED")
            if self.unit in {"day", "month"} and self.month is None:
                raise ValueError("MONTH_REQUIRED")
            if self.unit == "day" and self.day is None:
                raise ValueError("DAY_REQUIRED")
            if self.unit == "year" and self.month is not None or self.unit != "day" and self.day is not None:
                raise ValueError("EXCESS_OCCURRENCE_PRECISION")
            if self.unit == "day":
                date(self.year, self.month, self.day)
        return self

    def bounds(self, anchor: datetime) -> tuple[str | None, str | None, str]:
        if self.unit == "unknown":
            return None, None, "unknown"
        today = anchor.date()
        try:
            if self.offset is None:
                year, month = self.year, self.month
                start = date(year, month or 1, self.day or 1)
            elif self.unit == "day":
                start = today + timedelta(days=self.offset)
            elif self.unit == "week":
                start = today - timedelta(days=today.weekday()) + timedelta(weeks=self.offset)
                if self.weekday is not None:
                    start += timedelta(days=self.weekday)
            elif self.unit == "month":
                total = today.year * 12 + today.month - 1 + self.offset
                year, month0 = divmod(total, 12)
                start = date(year, month0 + 1, 1)
            else:
                start = date(today.year + self.offset, 1, 1)
            precision = "day" if self.weekday is not None else self.unit
            if precision == "day":
                end = start
            elif precision == "week":
                end = start + timedelta(days=6)
            elif precision == "month":
                end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
            else:
                end = date(start.year, 12, 31)
            # An occurred event cannot start in the future. Do not guess a correction.
            if start > today:
                return None, None, "unknown"
            return start.isoformat(), end.isoformat(), precision
        except (ValueError, OverflowError):
            return None, None, "unknown"


def explicit_occurrence(text: str) -> Occurrence:
    """Calendar syntax support for the existing offline extractor, not retrieval.

    The model can normalize other expressions through the same symbolic schema.
    Ambiguous/multiple time references stay unknown instead of picking the first.
    """
    choices = []
    patterns = [
        (r"(?<!\d)(\d{4})[-年](\d{1,2})[-月](\d{1,2})(?:[日号])?", "day"),
        (r"(?<!\d)(\d{4})年(\d{1,2})月(?!\d)", "month"),
        (r"(?<!\d)(\d{4})年(?!\d)", "year"),
    ]
    spans = []
    for pattern, unit in patterns:
        for match in re.finditer(pattern, text):
            if any(a <= match.start() < b for a, b in spans):
                continue
            values = dict(zip(("year", "month", "day"), map(int, match.groups())))
            try:
                choices.append(Occurrence(expression=match[0], unit=unit, **values))
            except ValueError:
                return Occurrence()
            spans.append(match.span())
    weekdays = "一二三四五六日天"
    for match in re.finditer(r"(上上|上|本|这)(?:周|星期|礼拜)([一二三四五六日天])?", text):
        suffix = match[2]
        choices.append(Occurrence(expression=match[0], unit="week",
            offset={"上上": -2, "上": -1, "本": 0, "这": 0}[match[1]],
            weekday=min(weekdays.index(suffix), 6) if suffix else None))
    for match in re.finditer(r"上上个?月|上个?月|本月|这个月|前年|去年|今年|大前天|前天|昨天|今日|今天|刚才|刚刚", text):
        word = match[0]
        if "月" in word:
            unit, offset = "month", -2 if word.startswith("上上") else -1 if word.startswith("上") else 0
        elif "年" in word:
            unit, offset = "year", {"前年": -2, "去年": -1, "今年": 0}[word]
        else:
            unit, offset = "day", {"大前天": -3, "前天": -2, "昨天": -1}.get(word, 0)
        choices.append(Occurrence(expression=word, unit=unit, offset=offset))
    if len(choices) != 1:
        return Occurrence()
    return choices[0]


def initialize_occurrence(db, table):
    if table not in {"memory_items", "events"}:
        raise ValueError("INVALID_OCCURRENCE_TABLE")
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    for name, definition in (("occurrence_start", "TEXT"), ("occurrence_end", "TEXT"),
                             ("occurrence_precision", "TEXT NOT NULL DEFAULT 'unknown'")):
        if name not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def item_interval(item) -> tuple[str | None, str | None, str]:
    """Only persisted occurrence metadata is trusted; legacy keys are unverified."""
    precision = item.get("occurrence_precision") or "unknown"
    return item.get("occurrence_start"), item.get("occurrence_end"), precision


def overlaps(item, start: date, end: date) -> bool:
    left, right, precision = item_interval(item)
    return bool(precision != "unknown" and left and right and left <= end.isoformat() and right >= start.isoformat())
