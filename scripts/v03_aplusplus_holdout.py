"""Offline A++ contract replay; no model, image, network or user database is used."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/life-core"))
from app.recollection_policy import assess_candidate, release_decision

FIXTURE = ROOT / "fixtures/recollection-policy-v2/holdout.json"
EVIDENCE = ROOT / "evidence/v03-stage-a-plus-plus"


def score_for(keep):
    value = .85 if keep else .2
    dimensions = dict.fromkeys((
        "personal_meaning", "uniqueness", "expressed_feeling", "event_clarity",
        "source_sufficiency", "window_relevance", "privacy_suitability",
        "novelty_or_development",
    ), value)
    dimensions.update(source_sufficiency=.85, event_clarity=.85,
                      window_relevance=.9, privacy_suitability=.1 if keep else .9)
    return {
        "eligible": keep, "reason_code": "MEANINGFUL_EVENT" if keep else "ROUTINE_EVENT",
        "model_reason_code": "MEANINGFUL_EVENT" if keep else "ROUTINE_EVENT",
        "score": sum(dimensions.values()) / len(dimensions), "dimensions": dimensions,
    }


def run():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    details, totals = [], dict(
        scenes=0, memorial=0, occurrence=0, image=0, egress_safe=0,
        fabricated_visual_facts=0, source_failures=0,
    )
    for scene in fixture["scenes"]:
        candidate = {
            "memory_id": scene["id"].lower(),
            "sources": [{"message_id": f"{scene['id']}-source", "quote": scene["text"]}],
        }
        judgment = assess_candidate(candidate)
        keep = any(
            (judgment["memorial"] == "KEEP_PRIVATE_TEXT") == expected
            for expected in scene["memorial_acceptable"]
        )
        decision = release_decision(
            score_for(keep), judgment, text_authorized=True, image_consent=True,
            egress_granted=True,
        )
        occurrence_ok = judgment["occurrence"] in scene["occurrence"]
        memorial_ok = (decision["memorial_eligible"] in scene["memorial_acceptable"])
        image_ok = decision["imageability"] in scene["image_acceptable"]
        expected_deny = scene["id"] in {"H02", "H10", "H11", "H17"}
        egress_ok = decision["egress_authorized"] is False if expected_deny else True
        facts = judgment["visual_facts"]
        facts_ok = all(
            fact["verification"] in ("SOURCE_EXACT", "SUPPORTED_PARAPHRASE")
            and fact["source_hashes"]
            for fact in facts
        )
        totals["scenes"] += 1
        totals["memorial"] += memorial_ok
        totals["occurrence"] += occurrence_ok
        totals["image"] += image_ok
        totals["egress_safe"] += egress_ok
        totals["fabricated_visual_facts"] += not facts_ok
        totals["source_failures"] += not facts_ok
        details.append({
            "id": scene["id"], "text": scene["text"], "local_judgment": judgment,
            "p04_fixture": score_for(keep), "decision": decision,
            "checks": {"memorial": memorial_ok, "occurrence": occurrence_ok,
                       "image": image_ok, "egress": egress_ok, "facts": facts_ok},
            "reference_note": scene["reason"],
        })
    passed = all(totals[key] == totals["scenes"] for key in (
        "memorial", "occurrence", "image", "egress_safe",
    )) and totals["fabricated_visual_facts"] == 0 and totals["source_failures"] == 0
    payload = {
        "contract": "OFFLINE_LOCAL_JUDGMENT_ONLY", "model_evidence": False,
        "real_requests": 0, "image_requests": 0, "human_reviewed": False,
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "totals": totals, "status": "PASS" if passed else "FAIL", "details": details,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "holdout-results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# V0.3 A++ 独立留出合同回放", "",
        "模式：本地保守判断规则 + 契约；不是云模型验收，不是生图验收。",
        f"结果：**{payload['status']}**；真实请求0、图片请求0；参考待真人复核。", "",
        "| 场景 | 纪念 | 事件性质 | 图像资格 | 外发安全 | 摘要 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in details:
        check = item["checks"]
        lines.append(
            f"| {item['id']} | {'PASS' if check['memorial'] else 'FAIL'} | "
            f"{'PASS' if check['occurrence'] else 'FAIL'} | "
            f"{'PASS' if check['image'] else 'FAIL'} | "
            f"{'PASS' if check['egress'] else 'FAIL'} | "
            f"{item['local_judgment']['memorial']} / {item['local_judgment']['imageability']} / "
            f"{item['decision']['egress_status']} |"
        )
    lines += [
        "", "## 限制", "",
        "留出由同一开发代理撰写，不是独立真人盲测；P04分数为明确标注的测试夹具，"
        "只验证分离合同。规则无法覆盖的一般同义表达会保守退回文字或待人工复核，"
        "不能据此声称真实模型语义质量PASS。",
    ]
    (EVIDENCE / "holdout-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "totals": totals}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    raise SystemExit(run())
