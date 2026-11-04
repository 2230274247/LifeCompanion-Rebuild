"""Conservative, evidence-anchored grouping of retellings for stage A."""
from __future__ import annotations

import json
import re
from datetime import datetime

from .memory import digest, normalized


ACTIONS = (
    (re.compile(r"跑步|晨跑|夜跑|跑了|跑过|跑"), "run"),
    (re.compile(r"散步|走走|走路"), "walk"),
    (re.compile(r"早餐|早饭"), "breakfast"),
    (re.compile(r"读书|看书|读完"), "reading"),
    (re.compile(r"加入.*项目组|项目组"), "project"),
)
PERIODS = (
    (re.compile(r"早晨|早上|清晨|上午"), "morning"),
    (re.compile(r"中午|午后|下午"), "afternoon"),
    (re.compile(r"傍晚|晚上|夜里|夜间"), "evening"),
)
REPEAT = re.compile(r"第二次|第三次|又一次|再一次|又(?:去|在|跑)|再(?:去|跑)")
DEICTIC = re.compile(r"那次|刚才(?:那次|的)?|刚刚(?:那次|的)?")
DISTANCE = re.compile(r"([一二三四五六七八九十两\d]+)\s*(?:公里|千米)")
NUMBERED_PLACE = re.compile(r"第([一二三四五六七八九十\d]+)(?:个|座)?(公园|餐厅|书店|咖啡馆)")
OTHER_PLACE = re.compile(r"另一(?:座|个|家|处)?(公园|餐厅|书店|咖啡馆)")


def _fact(text: str, mapping) -> set[str]:
    return {name for pattern, name in mapping if pattern.search(text)}


def facts(text: str) -> dict:
    places = set()
    if "公园" in text:
        places.add("park")
    if "餐厅" in text:
        places.add("restaurant")
    numbered = {f"第{number}{kind}" for number, kind in NUMBERED_PLACE.findall(text)}
    if numbered:
        places.update(numbered)
    if OTHER_PLACE.search(text):
        places.add("other-place")
    distances = {value for value in DISTANCE.findall(text)}
    return {
        "actions": _fact(text, ACTIONS),
        "periods": _fact(text, PERIODS),
        "places": places,
        "distances": distances,
        "repeat": bool(REPEAT.search(text)),
        "deictic": bool(DEICTIC.search(text)),
        "normalized": normalized(text),
    }


def _same_day(left: dict, right: dict) -> bool:
    return left.get("message_day") == right.get("message_day")


def _close(left: dict, right: dict, minutes: int = 120) -> bool:
    left_at, right_at = left.get("source_at"), right.get("source_at")
    if not left_at or not right_at:
        return False
    return abs((datetime.fromisoformat(left_at) - datetime.fromisoformat(right_at)).total_seconds()) <= minutes * 60


def _occurred_close(left: dict, right: dict, minutes: int = 30) -> bool:
    left_at, right_at = left.get("occurred_at"), right.get("occurred_at")
    if not left_at or not right_at:
        return True
    try:
        return abs(
            (datetime.fromisoformat(left_at) - datetime.fromisoformat(right_at)).total_seconds()
        ) <= minutes * 60
    except (TypeError, ValueError):
        return False


def same_occurrence(left: dict, right: dict) -> bool:
    a, b = left["semantics"], right["semantics"]
    if left.get("event_id") and left.get("event_id") == right.get("event_id"):
        return True
    if not a["actions"] or a["actions"] != b["actions"] or not _same_day(left, right):
        return False
    if a["repeat"] or b["repeat"] or a["periods"] and b["periods"] and a["periods"] != b["periods"]:
        return False
    place_difference = a["places"] ^ b["places"]
    if place_difference and (
        "other-place" in place_difference
        or any(place.startswith("第") for place in place_difference)
    ):
        return False
    if len(a["places"]) == 1 and len(b["places"]) == 1 and a["places"] != b["places"]:
        return False
    if a["distances"] and b["distances"] and a["distances"] != b["distances"]:
        return False
    explicit_reference = (a["deictic"] or b["deictic"]) and _close(left, right)
    if not explicit_reference and not _occurred_close(left, right):
        return False
    if a["normalized"] == b["normalized"]:
        return explicit_reference or _close(left, right, minutes=30)
    anchors = 0
    anchors += int(bool(a["periods"] and a["periods"] == b["periods"]))
    anchors += int(bool(a["places"] and a["places"] == b["places"]))
    anchors += int(bool(a["distances"] and a["distances"] == b["distances"]))
    return explicit_reference or anchors >= 3 or (
        anchors >= 2 and _close(left, right, minutes=30)
    )


def annotate(item: dict) -> dict:
    sources = sorted(item["sources"], key=lambda source: (source["message_at"], source["message_id"]))
    source_at = sources[0]["message_at"] if sources else item.get("occurred_at")
    try:
        message_day = datetime.fromisoformat(source_at).date().isoformat()
    except (TypeError, ValueError):
        message_day = None
    return {
        **item,
        "source_at": source_at,
        "message_day": message_day,
        "semantics": facts(item["text"]),
    }


def group_items(items: list[dict]) -> list[list[dict]]:
    annotated = [annotate(item) for item in items]
    def source_order(item):
        try:
            return datetime.fromisoformat(item["source_at"]).timestamp()
        except (TypeError, ValueError):
            return float("inf")

    annotated.sort(key=lambda item: (source_order(item), item["memory_id"]))
    groups = []
    for item in annotated:
        # Greedy full compatibility prevents an ambiguous A-B-C bridge from
        # transitively merging A and C when their own evidence disagrees.
        for group in groups:
            if all(same_occurrence(item, member) for member in group):
                group.append(item)
                break
        else:
            groups.append([item])
    return groups


def merge_group(group: list[dict]) -> dict:
    ordered = sorted(group, key=lambda item: (item["source_at"], item["memory_id"]))
    representative = ordered[0]
    sources = {
        source["message_id"]: source
        for item in ordered
        for source in item["sources"]
    }
    merged_sources = sorted(sources.values(), key=lambda source: (source["message_at"], source["message_id"]))
    memory_ids = [item["memory_id"] for item in ordered]
    texts = list(dict.fromkeys(item["text"] for item in ordered))
    value = {
        **representative,
        "memory_id": representative["memory_id"],
        "memory_ids": memory_ids,
        "revision": max(item["revision"] for item in ordered),
        "source_revisions": {item["memory_id"]: item["revision"] for item in ordered},
        "text": "\n".join(texts),
        "sources": merged_sources,
        "group_key": "grp_" + digest("|".join(memory_ids))[:24],
    }
    for key in ("source_at", "message_day", "semantics"):
        value.pop(key, None)
    value["input_hash"] = digest(
        json.dumps(
            {
                "memory_ids": memory_ids,
                "event_id": value.get("event_id"),
                "occurred_at": value.get("occurred_at"),
                "revision": value["revision"],
                "source_revisions": value["source_revisions"],
                "text": value["text"],
                "sources": merged_sources,
            },
            sort_keys=True, ensure_ascii=False)
    )
    return value
