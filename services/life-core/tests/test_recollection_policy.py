"""A++ separation contract; fixtures are offline judgments, not model evidence."""
import pytest

from app.recollection_policy import assess_candidate, release_decision, validate_judgment


SOURCE = {
    "memory_id": "m1",
    "sources": [{
        "message_id": "source-1",
        "quote": "今天在公园跑了三公里，回家后很开心。",
    }],
}


def judgment(**changes):
    value = {
        "occurrence": "SELF_OCCURRED",
        "memorial": "KEEP_PRIVATE_TEXT",
        "imageability": "TEXT_ONLY",
        "egress_preference": "UNSPECIFIED",
        "memorial_reason": "用户明确表达的内在进展",
        "image_reason": "没有足够的具体可见事实",
        "visual_facts": [],
    }
    value.update(changes)
    return value


def score(*, eligible=True, reason="MEANINGFUL_EVENT", privacy=.95):
    return {
        "eligible": eligible,
        "reason_code": reason,
        "model_reason_code": reason,
        "score": .8,
        "dimensions": {
            "personal_meaning": .9,
            "uniqueness": .7,
            "expressed_feeling": .7,
            "event_clarity": .8,
            "source_sufficiency": .9,
            "window_relevance": .9,
            "privacy_suitability": privacy,
            "novelty_or_development": .7,
        },
    }


def test_s33_keeps_private_text_even_when_p04_privacy_gate_rejects_image():
    result = release_decision(
        score(eligible=False, reason="PRIVATE_OR_SENSITIVE", privacy=.1),
        judgment(),
        text_authorized=True,
        image_consent=True,
    )
    assert result["memorial_eligible"] is True
    assert result["storage_status"] == "PRIVATE_TEXT"
    assert result["image_content_eligible"] is False
    assert result["egress_authorized"] is False


def test_other_person_secret_is_neither_automatic_memorial_nor_egress():
    result = release_decision(
        score(),
        judgment(
            occurrence="OTHER_OCCURRED",
            memorial="SKIP",
            imageability="PRIVATE_SKIP",
            egress_preference="DENY",
        ),
        text_authorized=True,
        image_consent=True,
    )
    assert result["memorial_eligible"] is False
    assert result["storage_status"] == "SKIP"
    assert result["reason_code"] == "OTHER_PERSON_PRIVATE"
    assert result["egress_authorized"] is False


@pytest.mark.parametrize(
    "occurrence,reason",
    [
        ("PLANNED", "NON_OCCURRED_FUTURE"),
        ("QUOTED_OR_GENERATED", "NOT_SELF_OBSERVED_EVENT"),
        ("UNCERTAIN", "EVENT_NOT_CONFIRMED"),
    ],
)
def test_non_events_use_factual_status_not_privacy_refusal(occurrence, reason):
    result = release_decision(
        score(eligible=False, reason="NO_CLEAR_EVENT"),
        judgment(
            occurrence=occurrence,
            memorial="SKIP",
            imageability="NOT_APPLICABLE",
        ),
        text_authorized=True,
        image_consent=True,
    )
    assert result["reason_code"] == reason
    assert result["imageability"] == "NOT_APPLICABLE"
    assert "PRIVATE" not in result["reason_code"]


def test_image_eligibility_and_egress_authorization_are_independent():
    safe = judgment(
        imageability="SAFE_SCENE",
        visual_facts=[{
            "fact_type": "ACTION",
            "statement": "在公园跑步",
            "source_message_ids": ["source-1"],
            "source_span": "在公园跑了三公里",
        }],
    )
    no_consent = release_decision(
        score(), safe, text_authorized=True, image_consent=False,
    )
    assert no_consent["memorial_eligible"] is True
    assert no_consent["image_content_eligible"] is True
    assert no_consent["egress_status"] == "NOT_AUTHORIZED"
    assert no_consent["egress_authorized"] is False

    denied = release_decision(
        score(),
        judgment(
            egress_preference="DENY",
            imageability="SAFE_SCENE",
            visual_facts=safe["visual_facts"],
        ),
        text_authorized=True,
        image_consent=True,
    )
    assert denied["image_content_eligible"] is True
    assert denied["egress_status"] == "EVENT_DENIED"
    assert denied["egress_authorized"] is False

    authorized = release_decision(
        score(), safe, text_authorized=True, image_consent=True, egress_granted=True,
    )
    assert authorized["image_content_eligible"] is True
    assert authorized["egress_status"] == "AUTHORIZED"
    assert authorized["image_dispatch_allowed"] is True


def test_model_grounded_open_action_is_not_reduced_to_fixed_action_vocabulary():
    text = "今天下午我给阳台上的多肉一盆盆换了新土，手指沾满泥，但心里很踏实。"
    result = assess_candidate({
        "memory_id": "m-open",
        "model_validated": True,
        "sources": [{"message_id": "q-open", "quote": text}],
    })
    assert result["occurrence"] == "SELF_OCCURRED"
    assert result["imageability"] == "SAFE_SCENE"
    assert result["assessment_mode"] == "MODEL_EVENT_EXACT_SOURCE_GROUNDING"
    assert result["visual_facts"][0]["canonical_fact"]["action_text"].startswith(
        "今天下午我给阳台上的多肉"
    )


def test_grounded_action_paraphrase_is_allowed_with_exact_audit_span():
    value = judgment(
        imageability="SAFE_SCENE",
        visual_facts=[{
            "fact_type": "ACTION",
            "statement": "在公园跑步",
            "source_message_ids": ["source-1"],
            "source_span": "在公园跑了三公里",
        }],
    )
    checked = validate_judgment(value, SOURCE)
    assert checked["visual_facts"][0]["verification"] == "SUPPORTED_PARAPHRASE"


@pytest.mark.parametrize(
    "fact",
    [
        {
            "fact_type": "WEATHER",
            "statement": "晴天",
            "source_message_ids": ["source-1"],
            "source_span": "在公园跑了三公里",
        },
        {
            "fact_type": "CLOTHING",
            "statement": "穿红色运动服",
            "source_message_ids": ["source-1"],
            "source_span": "在公园跑了三公里",
        },
        {
            "fact_type": "LOCATION",
            "statement": "河边",
            "source_message_ids": ["source-1"],
            "source_span": "在公园跑了三公里",
        },
        {
            "fact_type": "ACTION",
            "statement": "在晴天公园穿运动服跑步",
            "source_message_ids": ["source-1"],
            "source_span": "在公园跑了三公里",
        },
    ],
)
def test_unverified_people_places_clothing_weather_are_rejected(fact):
    with pytest.raises(ValueError, match="VISUAL_FACT_UNSUPPORTED"):
        validate_judgment(
            judgment(imageability="SAFE_SCENE", visual_facts=[fact]),
            SOURCE,
        )


def test_safe_scene_without_facts_or_with_foreign_source_is_rejected():
    with pytest.raises(ValueError, match="SAFE_SCENE_REQUIRES_FACTS"):
        validate_judgment(judgment(imageability="SAFE_SCENE"), SOURCE)
    with pytest.raises(ValueError, match="VISUAL_SOURCE_UNSUPPORTED"):
        validate_judgment(
            judgment(
                imageability="SAFE_SCENE",
                visual_facts=[{
                    "fact_type": "ACTION",
                    "statement": "跑步",
                    "source_message_ids": ["foreign"],
                    "source_span": "在公园跑了三公里",
                }],
            ),
            SOURCE,
        )
