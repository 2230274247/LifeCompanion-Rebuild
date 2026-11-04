"""Independent local memorial, visual-grounding and purpose-consent contracts."""
from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VERSION = "recollection-policy-v2"
FACT_VERSION = "visual-grounding-v1"
CONSENT_VERSION = "recollection-egress-v1"
PRIVATE = re.compile(r"医疗|病情|诊断|治疗|债务|金融|银行卡|密码|住址|家庭秘密|离婚")
OTHER = re.compile(r"(?:朋友|同事|他|她|家人).*(?:告诉我|私下|保密|病情|离婚)")
DENY = re.compile(r"不(?:要|愿|想).{0,12}(?:外部|外发|其他服务|发给|生图)|"
                  r"只(?:希望|想|要).{0,8}(?:文字|私下|私密)|仅.{0,6}文字")
TEXT_REQUEST = re.compile(r"想记住|想记下|记下来|记录下来|留下文字|留一段文字|"
                          r"私下记录|为.{0,20}留.{0,4}文字|很值得记住")
NO_MEMORIAL = re.compile(r"不要(?:自动)?(?:记录|纪念|记住)|别记|不要记")
UNCERTAIN = re.compile(r"好像|似乎|不确定|还没确认|未确认|也许|不知道|是否|可能")
FUTURE = re.compile(r"(?:明天|下周|下个月|如果|计划).*(?:还没|没开始|没有去|没去|只是想象)|"
                    r"^(?:我计划|我打算|如果|明天|下周)")
QUOTED = re.compile(r"(?:转贴|转发|引用|AI|模型).{0,10}(?:建议|故事|回答|虚构)")
INNER = re.compile(r"内心|思念|接纳自己|原谅.{0,8}自己|自己的边界|尊重自己的边界|人生节奏")
NONFACT = {
    "PLANNED": "NON_OCCURRED_FUTURE",
    "QUOTED_OR_GENERATED": "NOT_SELF_OBSERVED_EVENT",
    "UNCERTAIN": "EVENT_NOT_CONFIRMED",
    "UNKNOWN": "SOURCE_REVIEW_REQUIRED",
}


class VisualFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fact_type: Literal["ACTION", "OBJECT", "LOCATION", "PERSON", "CLOTHING", "WEATHER"]
    statement: str = Field(min_length=1, max_length=160)
    source_message_ids: list[str] = Field(min_length=1, max_length=4)
    source_span: str = Field(min_length=1, max_length=500)


class Judgment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    occurrence: Literal[
        "SELF_OCCURRED", "SELF_INNER_CHANGE", "OTHER_OCCURRED",
        "PLANNED", "QUOTED_OR_GENERATED", "UNCERTAIN", "UNKNOWN",
    ]
    memorial: Literal["KEEP_PRIVATE_TEXT", "SKIP"]
    imageability: Literal["SAFE_SCENE", "TEXT_ONLY", "PRIVATE_SKIP", "NOT_APPLICABLE"]
    egress_preference: Literal["UNSPECIFIED", "DENY"]
    memorial_reason: str = Field(min_length=1, max_length=400)
    image_reason: str = Field(min_length=1, max_length=400)
    visual_facts: list[VisualFact] = Field(default_factory=list, max_length=8)


def _action(value):
    """Parse a bounded assertion; omitted attributes are allowed, additions are not."""
    text = re.sub(r"^(?:今天|今日|早上|早晨|上午|刚才)", "", value.strip().rstrip("。"))
    match = re.fullmatch(
        r"(?:在(?P<place>[^，。；穿和与]{1,20}?))?"
        r"(?P<verb>跑步|慢跑|跑完|跑了|散步|步行|走路|走完|走了)"
        r"(?P<distance>[一二三四五六七八九十百零\d.]+(?:公里|千米|米))?", text,
    )
    if match:
        verb = match["verb"]
        result = {"action": "RUN" if verb.startswith(("跑", "慢")) else "WALK"}
        if verb == "慢跑":
            result["pace"] = "SLOW"
        if match["place"]:
            result["location"] = match["place"]
        if match["distance"]:
            result["distance"] = match["distance"].replace("千米", "公里")
        return result
    match = re.fullmatch(r"(?P<independent>独立|自己)?修好(?:了)?(?:家里的)?(?P<old>旧)?(?P<object>收音机|自行车|台灯)", text)
    if match:
        result = {"action": "REPAIR", "object": match["object"]}
        if match["independent"]:
            result["independent"] = True
        if match["old"]:
            result["condition"] = "OLD"
        return result
    return None


def _canonical(kind, value, quote):
    if kind == "ACTION":
        return _action(value)
    if kind == "WEATHER":
        meanings = {
            "晴天": "SUNNY", "天气晴朗": "SUNNY",
            "下雨": "RAIN", "雨天": "RAIN",
            "下雪": "SNOW", "雪天": "SNOW",
        }
        return {"weather": meanings[value]} if value in meanings else None
    if kind == "LOCATION":
        if re.search(r"(?:在|去|到|位于)" + re.escape(value), quote):
            return {"location": value}
        return None
    if kind == "OBJECT":
        return {"object": value} if value in (
            "收音机", "旧收音机", "自行车", "台灯", "书", "兰花", "番茄",
        ) else None
    if kind == "PERSON":
        if re.search(r"(?:和|与|同)" + re.escape(value) + r"(?:一起|在|去|吃|散步|跑)", quote):
            return {"person": value}
        return None
    if kind == "CLOTHING":
        match = re.fullmatch(r"(?:穿着?|身穿)(.+)", value)
        return {"clothing": match[1]} if match else None
    return None


def verify_visual_fact(fact, sources, *, model_validated=False):
    value = VisualFact.model_validate(fact)
    quotes = {s["message_id"]: s["quote"] for s in sources}
    if len(set(value.source_message_ids)) != len(value.source_message_ids):
        raise ValueError("VISUAL_SOURCE_UNSUPPORTED")
    if not set(value.source_message_ids) <= set(quotes):
        raise ValueError("VISUAL_SOURCE_UNSUPPORTED")
    matched = [quotes[key] for key in value.source_message_ids
               if value.source_span in quotes[key]]
    if len(matched) != len(value.source_message_ids):
        raise ValueError("VISUAL_SOURCE_UNSUPPORTED")
    for quote in matched:
        if not model_validated and (
            UNCERTAIN.search(quote) or FUTURE.search(quote) or QUOTED.search(quote)
            or re.search(r"没有|没去|并未|并没有|没看到|没穿|不穿|不是|并非|不曾", quote)
        ):
            raise ValueError("VISUAL_FACT_UNSUPPORTED")
        claim = _canonical(value.fact_type, value.statement, quote)
        source = _canonical(value.fact_type, value.source_span, quote)
        if (
            (not claim or not source)
            and model_validated
            and value.fact_type == "ACTION"
            and value.statement in value.source_span
        ):
            claim = source = {"action_text": " ".join(value.statement.split())}
        if not claim or not source or any(source.get(k) != v for k, v in claim.items()):
            raise ValueError("VISUAL_FACT_UNSUPPORTED")
    return {
        **value.model_dump(),
        "verification": (
            "SOURCE_EXACT" if value.statement == value.source_span else "SUPPORTED_PARAPHRASE"
        ),
        "canonical_fact": claim,
        "verifier_version": FACT_VERSION,
        "source_hashes": {
            key: hashlib.sha256(quotes[key].encode("utf-8")).hexdigest()
            for key in value.source_message_ids
        },
    }


def validate_judgment(value, candidate):
    parsed = Judgment.model_validate(value)
    result = parsed.model_dump()
    model_validated = bool(candidate.get("model_validated"))
    if parsed.imageability == "SAFE_SCENE" and not parsed.visual_facts:
        raise ValueError("SAFE_SCENE_REQUIRES_FACTS")
    if parsed.imageability != "SAFE_SCENE" and parsed.visual_facts:
        raise ValueError("NON_SCENE_WITH_VISUAL_FACTS")
    result["visual_facts"] = [
        verify_visual_fact(
            fact.model_dump(), candidate["sources"],
            model_validated=model_validated,
        )
        for fact in parsed.visual_facts
    ]
    if parsed.imageability == "SAFE_SCENE" and not any(
        fact["fact_type"] in ("ACTION", "OBJECT") for fact in result["visual_facts"]
    ):
        raise ValueError("SAFE_SCENE_REQUIRES_ACTION_OR_OBJECT")
    result["contract_version"] = VERSION
    return result


def assess_candidate(candidate):
    """Local conservative adapter for stored occurred events, never a cloud fallback."""
    quotes = [s["quote"] for s in candidate["sources"]]
    text = "\n".join(quotes)
    model_validated = bool(candidate.get("model_validated"))
    occurrence = "SELF_OCCURRED"
    memorial, imageability = "KEEP_PRIVATE_TEXT", "TEXT_ONLY"
    reason, image_reason = "沿用已保存的本人事件，纪念准入仍由P04判定", "尚无已核验视觉事实"
    if not model_validated and QUOTED.search(text):
        occurrence = "QUOTED_OR_GENERATED"
    elif not model_validated and UNCERTAIN.search(text):
        occurrence = "UNCERTAIN"
    elif not model_validated and FUTURE.search(text):
        occurrence = "PLANNED"
    elif PRIVATE.search(text) and OTHER.search(text):
        occurrence = "OTHER_OCCURRED"
    elif PRIVATE.search(text) and not re.search(r"我的|自己的|我自己|我(?:还清|确诊|决定|治疗)", text):
        occurrence = "UNKNOWN"
    elif INNER.search(text):
        occurrence = "SELF_INNER_CHANGE"
    if occurrence in NONFACT:
        memorial, imageability, reason = "SKIP", "NOT_APPLICABLE", NONFACT[occurrence]
    elif occurrence == "OTHER_OCCURRED":
        memorial, imageability, reason = "SKIP", "PRIVATE_SKIP", "OTHER_PERSON_PRIVATE"
    elif PRIVATE.search(text):
        imageability, image_reason = "PRIVATE_SKIP", "私人或敏感内容不自动形成图片"
    if NO_MEMORIAL.search(text):
        memorial, reason = "SKIP", "USER_DECLINED_MEMORIAL"
    facts = []
    if imageability == "TEXT_ONLY" and occurrence == "SELF_OCCURRED":
        for source in candidate["sources"]:
            for clause in re.split(r"[，。；！\n]", source["quote"]):
                clause = clause.strip()
                if _action(clause):
                    fact = {
                        "fact_type": "ACTION", "statement": clause,
                        "source_message_ids": [source["message_id"]], "source_span": clause,
                    }
                    try:
                        verify_visual_fact(
                            fact, candidate["sources"],
                            model_validated=model_validated,
                        )
                    except ValueError:
                        continue
                    facts.append(fact)
        if not facts and model_validated:
            for source in candidate["sources"]:
                clause = next((
                    value.strip()
                    for value in re.split(r"[，。；！\n]", source["quote"])
                    if value.strip()
                ), "")
                if not clause or len(clause) > 500:
                    continue
                fact = {
                    "fact_type": "ACTION",
                    "statement": clause,
                    "source_message_ids": [source["message_id"]],
                    "source_span": clause,
                }
                try:
                    verify_visual_fact(
                        fact, candidate["sources"], model_validated=True
                    )
                except ValueError:
                    continue
                facts.append(fact)
                break
        if facts:
            imageability, image_reason = "SAFE_SCENE", "仅使用带类型、来源片段和核验规则的明确动作事实"
    value = {
        "occurrence": occurrence, "memorial": memorial, "imageability": imageability,
        "egress_preference": "DENY" if DENY.search(text) or occurrence == "OTHER_OCCURRED" else "UNSPECIFIED",
        "memorial_reason": reason, "image_reason": image_reason, "visual_facts": facts[:8],
    }
    result = validate_judgment(value, candidate)
    result["explicit_private_request"] = bool(
        TEXT_REQUEST.search(text)
        and (DENY.search(text) or imageability in ("TEXT_ONLY", "PRIVATE_SKIP"))
        and memorial == "KEEP_PRIVATE_TEXT"
    )
    result["assessment_mode"] = (
        "MODEL_EVENT_EXACT_SOURCE_GROUNDING"
        if model_validated else "LOCAL_CONSERVATIVE_RULES"
    )
    return result


def release_decision(scored, judgment, *, text_authorized, image_consent,
                     egress_granted=False):
    """Preserve scores; neither privacy dimensions nor model KEEP grants permission."""
    occurrence = judgment["occurrence"]
    reason = NONFACT.get(occurrence)
    if occurrence == "OTHER_OCCURRED":
        reason = "OTHER_PERSON_PRIVATE"
    if not reason and judgment["memorial"] == "SKIP":
        reason = "USER_OR_POLICY_DECLINED"
    if not reason and scored is not None:
        for dimension, minimum, code in (
            ("source_sufficiency", .8, "SOURCE_INSUFFICIENT"),
            ("event_clarity", .6, "NO_CLEAR_EVENT"),
            ("window_relevance", .6, "OUTSIDE_WINDOW"),
            ("personal_meaning", .4, "LOW_PERSONAL_MEANING"),
            ("novelty_or_development", .3, "DUPLICATE_EVENT"),
        ):
            if scored["dimensions"][dimension] < minimum:
                reason = code
                break
        if not reason and (
            scored.get("model_reason_code", scored["reason_code"])
            not in ("MEANINGFUL_EVENT", "PRIVATE_OR_SENSITIVE")
        ):
            reason = scored.get("model_reason_code", scored["reason_code"])
    elif not reason and not judgment.get("explicit_private_request"):
        reason = "P04_NOT_AVAILABLE"
    memorial = reason is None
    image = bool(judgment["imageability"] == "SAFE_SCENE" and judgment["visual_facts"]
                 and occurrence == "SELF_OCCURRED")
    denied = judgment["egress_preference"] == "DENY" or judgment["imageability"] == "PRIVATE_SKIP"
    egress = bool(image and egress_granted and image_consent and not denied)
    stored = memorial and text_authorized
    return {
        "contract_version": VERSION,
        "memorial_eligible": memorial,
        "text_storage_authorized": bool(text_authorized),
        "storage_status": "PRIVATE_TEXT" if stored else "SKIP",
        "reason_code": reason or (
            "P04_PRIVATE_TEXT_ELIGIBLE"
            if scored and scored.get("model_reason_code") == "PRIVATE_OR_SENSITIVE"
            else "P04_MEANINGFUL_EVENT" if scored
            else "USER_REQUESTED_PRIVATE_TEXT"
        ),
        "imageability": judgment["imageability"],
        "image_content_eligible": image,
        "image_reason": judgment["image_reason"],
        "egress_authorized": egress,
        "egress_status": (
            "EVENT_DENIED" if denied else
            "AUTHORIZED" if egress else
            "NOT_AUTHORIZED" if image else "NOT_APPLICABLE"
        ),
        "image_dispatch_allowed": bool(stored and image and egress),
        "judgment": judgment,
    }
