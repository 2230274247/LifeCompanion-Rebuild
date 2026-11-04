"""Model-led open-language event semantics with deterministic grounding checks."""
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.memory import Candidate
from test_api import bootstrap, make_app


NOW = datetime.fromisoformat("2026-11-04T15:00:00+08:00")


def install_model(monkeypatch, candidate):
    class Model:
        def __init__(self, **_kwargs):
            pass

    class Manager:
        def invoke(self, _state, config=None):
            return [SimpleNamespace(content=candidate)]

    monkeypatch.setattr("langchain_openai.ChatOpenAI", Model)
    monkeypatch.setattr("langmem.create_memory_manager", lambda *_a, **_kw: Manager())


def event(text, *, owner="self", state="occurred"):
    return Candidate(
        candidate_type="life_event",
        canonical_text=text,
        evidence_quote=text,
        occurred_state=state,
        experience_owner=owner,
        confidence=.9,
        sensitivity="ordinary",
        image_candidate=False,
    )


@pytest.mark.parametrize(
    "text",
    [
        "今天下午我给阳台上的多肉一盆盆换了新土，手指沾满泥，但心里很踏实。",
        "午后把吊兰挪到光线更柔和的角落，顺手用软布擦掉了叶片上的灰。",
        "今天没下雨，我还是按原计划把旧木架重新摆好，屋里一下显得宽敞了。",
        "忙完这一阵，屋里终于安静下来，我坐在窗边发了会儿呆。",
    ],
)
def test_model_led_open_actions_are_not_second_guessed_by_rule_vocabulary(
    tmp_path, monkeypatch, text
):
    app, client = make_app(tmp_path)
    with client:
        memory = app.state.memory
        memory.settings = replace(memory.settings, memory_llm_key="synthetic")
        install_model(monkeypatch, event(text))
        candidate, reason = memory.classify(
            text,
            NOW,
            use_llm=True,
            user_id="owner",
            source_message_id="open-language",
        )
    assert reason == "llm_validated"
    assert candidate.canonical_text == text
    assert candidate.image_candidate is True


@pytest.mark.parametrize(
    "owner,state,reason",
    [
        ("other", "occurred", "other_experience"),
        ("quoted", "occurred", "quoted_content"),
        ("ai", "occurred", "ai_generated"),
        ("hypothetical", "hypothetical", "hypothetical"),
        ("self", "planned", "future_plan"),
        ("self", "uncertain", "uncertain"),
    ],
)
def test_model_must_distinguish_non_self_future_and_uncertain_content(
    tmp_path, monkeypatch, owner, state, reason
):
    text = "如果明天天气合适，我可能会去河边拍一组照片。"
    app, client = make_app(tmp_path)
    with client:
        memory = app.state.memory
        memory.settings = replace(memory.settings, memory_llm_key="synthetic")
        install_model(monkeypatch, event(text, owner=owner, state=state))
        candidate, actual = memory.classify(
            text,
            NOW,
            use_llm=True,
            user_id="owner",
            source_message_id="non-event",
        )
    assert candidate is None
    assert actual == reason


def test_model_output_must_still_copy_exact_source_evidence(tmp_path, monkeypatch):
    text = "今天给窗边的多肉换了新土。"
    fabricated = event(text)
    fabricated.evidence_quote = "今天和朋友去海边冲浪。"
    app, client = make_app(tmp_path)
    with client:
        memory = app.state.memory
        memory.settings = replace(memory.settings, memory_llm_key="synthetic")
        install_model(monkeypatch, fabricated)
        with pytest.raises(ValueError, match="MEMORY_UNGROUNDED_OUTPUT"):
            memory.classify(
                text,
                NOW,
                use_llm=True,
                user_id="owner",
                source_message_id="fabricated",
            )


def test_multi_turn_supplement_keeps_original_event_and_adds_evidence(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        owner = user["life_user_id"]
        memory = app.state.memory
        first = "今天下午我给阳台上的多肉一盆盆换了新土，手指沾满泥，但心里很踏实。"
        supplement = "记住刚才那件事，旁边还放着一只蓝色喷壶。"
        event_row = app.state.store.create_event(
            user_id=owner,
            source_type="chat",
            source_message_ids=["turn-one"],
            conversation_id="multi-turn",
            occurred_at=NOW.isoformat(),
            title="换盆",
            summary=first,
            confidence=.9,
            consent_state="granted",
            status="published",
            idempotency_key=f"{owner}:turn-one",
        )
        item = memory.save(
            owner,
            event(first),
            memory.key_for(event(first), first, NOW),
            "turn-one",
            "multi-turn",
            first,
            NOW,
            event_row["event_id"],
        )
        context = memory.contextual_event(owner, "multi-turn", supplement, NOW)
        assert context["memory_id"] == item["memory_id"]
        merged = Candidate(
            candidate_type="life_event",
            canonical_text=context["canonical_text"],
            evidence_quote=supplement,
            occurred_state="occurred",
            experience_owner="self",
            confidence=context["confidence"],
            sensitivity=context["sensitivity"],
            image_candidate=True,
        )
        memory.save(
            owner,
            merged,
            context["semantic_key"],
            "turn-two",
            "multi-turn",
            supplement,
            NOW,
            context["event_id"],
        )
        detail = memory.detail(owner, item["memory_id"])
    assert detail["canonical_text"] == first
    assert {source["message_id"] for source in detail["sources"]} == {
        "turn-one",
        "turn-two",
    }


def test_model_subspan_does_not_truncate_persisted_source_evidence(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        owner = user["life_user_id"]
        text = (
            "今天下午我给阳台上的多肉一盆盆换了新土，手指沾满泥，"
            "旁边有黄色马克杯和蓝色喷壶，阳光暖暖的，我心里很踏实。"
        )
        candidate = event(text)
        candidate.evidence_quote = text.split("，", 1)[0]
        item = app.state.memory.save(
            owner,
            candidate,
            app.state.memory.key_for(candidate, text, NOW),
            "full-source-evidence",
            "open-language",
            text,
            NOW,
        )
        with app.state.store.connect() as db:
            stored = db.execute(
                "SELECT evidence_quote FROM memory_evidence WHERE memory_id=?",
                (item["memory_id"],),
            ).fetchone()
    assert stored["evidence_quote"] == text
