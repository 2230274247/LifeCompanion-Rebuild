"""Grounded DeepSeek prompt generation is bounded, exact and independently audited."""
from dataclasses import replace
import json

import httpx
import pytest

from app.recollection_prompt import (
    PromptBlocked,
    PromptFailed,
    RecollectionPromptGenerator,
    validate_prompt_output,
)

from test_api import make_app


TEXT = (
    "今天下午我在阳台给绿萝浇水，旁边有黄色马克杯和蓝色笔记本，"
    "阳光暖暖的，我觉得很平静。"
)
PROMPT = (
    "竖幅生活纪实摄影，午后阳台上的绿萝正在被浇水，叶片旁放着黄色马克杯和"
    "蓝色笔记本，温暖阳光落在桌面与植物上，氛围安静平和，自然光影，"
    "构图克制，不出现人物正脸、文字、水印或品牌标志。"
)


def candidate():
    return {
        "memory_id": "mem_prompt_fixture",
        "text": TEXT,
        "occurred_at": "2026-11-04T07:00:00+00:00",
        "sources": [
            {
                "message_id": "message-prompt-fixture",
                "quote": TEXT,
                "message_at": "2026-11-04T07:00:00+00:00",
            }
        ],
    }


def provider_response(output=None):
    return httpx.Response(
        200,
        json={
            "id": "deepseek-response-fixture",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            output
                            or {
                                "prompt": PROMPT,
                                "grounded_visual_facts": [
                                    "绿萝",
                                    "黄色马克杯",
                                    "蓝色笔记本",
                                ],
                            },
                            ensure_ascii=False,
                        )
                    },
                }
            ],
            "usage": {"prompt_tokens": 123, "completion_tokens": 45},
        },
    )


def test_prompt_call_records_exact_input_output_and_reuses_without_retry(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        settings = replace(
            app.state.settings,
            memory_llm_key="synthetic-deepseek-key",
            moment_prompt_request_budget=1,
        )
        requests = []

        def respond(request):
            requests.append(request)
            return provider_response()

        generator = RecollectionPromptGenerator(
            app.state.store,
            settings,
            transport=httpx.MockTransport(respond),
        )
        result = generator.generate(
            "owner",
            "moment-prompt-a",
            candidate(),
            check_egress=lambda: True,
        )
        assert result["prompt"] == PROMPT
        assert result["cached"] is False
        cached = generator.generate(
            "owner",
            "moment-prompt-a",
            candidate(),
            check_egress=lambda: True,
        )
        assert cached["cached"] is True and cached["prompt"] == PROMPT
        assert len(requests) == 1

        with app.state.store.connect() as db:
            row = db.execute(
                "SELECT * FROM recollection_prompt_calls WHERE moment_id=?",
                ("moment-prompt-a",),
            ).fetchone()
        assert row["status"] == "succeeded"
        assert row["input_tokens"] == 123 and row["output_tokens"] == 45
        assert row["response_id"] == "deepseek-response-fixture"
        recorded_input = json.loads(row["input_json"])
        assert recorded_input["messages"][1]["content"]
        assert "逐字子串" in recorded_input["messages"][0]["content"]
        assert json.loads(row["raw_output"])["prompt"] == PROMPT
        assert "synthetic-deepseek-key" not in row["input_json"]

        with pytest.raises(PromptBlocked, match="PROMPT_REQUEST_BUDGET"):
            generator.generate(
                "owner",
                "moment-prompt-b",
                candidate(),
                check_egress=lambda: True,
            )
        assert len(requests) == 1


def test_ungrounded_prompt_output_is_rejected_and_never_retried(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        settings = replace(
            app.state.settings,
            memory_llm_key="synthetic",
            moment_prompt_request_budget=2,
        )
        requests = []

        def respond(request):
            requests.append(request)
            return provider_response(
                {
                    "prompt": PROMPT + "窗边还有一只不存在的猫。",
                    "grounded_visual_facts": ["不存在的猫"],
                }
            )

        generator = RecollectionPromptGenerator(
            app.state.store,
            settings,
            transport=httpx.MockTransport(respond),
        )
        with pytest.raises(PromptFailed, match="PROMPT_UNGROUNDED_VISUAL_FACT"):
            generator.generate(
                "owner",
                "moment-prompt-invalid",
                candidate(),
                check_egress=lambda: True,
            )
        with pytest.raises(PromptBlocked, match="PROMPT_ALREADY_ATTEMPTED"):
            generator.generate(
                "owner",
                "moment-prompt-invalid",
                candidate(),
                check_egress=lambda: True,
            )
        assert len(requests) == 1
        with app.state.store.connect() as db:
            row = db.execute(
                "SELECT * FROM recollection_prompt_calls WHERE moment_id=?",
                ("moment-prompt-invalid",),
            ).fetchone()
        assert row["status"] == "failed"
        assert row["error_code"] == "PROMPT_UNGROUNDED_VISUAL_FACT"
        assert row["output_prompt"] is None


@pytest.mark.parametrize(
    "output,error",
    [
        (
            {"prompt": PROMPT, "grounded_visual_facts": ["一只猫"]},
            "PROMPT_UNGROUNDED_VISUAL_FACT",
        ),
        (
            {"prompt": PROMPT, "grounded_visual_facts": ["绿萝", "一只猫"]},
            "PROMPT_UNGROUNDED_VISUAL_FACT",
        ),
    ],
)
def test_every_declared_visual_fact_must_come_verbatim_from_source(output, error):
    with pytest.raises(PromptFailed, match=error):
        validate_prompt_output(output, candidate())


def test_prompt_is_deterministically_augmented_when_model_omits_exact_fact_text():
    original = PROMPT.replace("蓝色笔记本", "")
    output = validate_prompt_output(
        {
            "prompt": original,
            "grounded_visual_facts": ["绿萝", "黄色马克杯", "蓝色笔记本"],
        },
        candidate(),
    )
    assert output.prompt != original
    assert output.prompt.endswith("画面必须准确呈现以下来源事实：蓝色笔记本。")
    for fact in output.grounded_visual_facts:
        assert fact in output.prompt
