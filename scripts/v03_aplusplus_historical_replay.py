"""Replay A++ separation over frozen P04 outputs without another model request."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/life-core"))
from app.recollection_policy import assess_candidate, release_decision

CASES = ROOT / "evidence/v03-stage-a-plus/frozen-cases.json"
REFERENCE_V2 = ROOT / "fixtures/recollection-policy-v2/reference-v2-draft.json"
PHASES = ("baseline", "retest")
OUTPUT = ROOT / "evidence/v03-stage-a-plus-plus"


def event_by_source(case):
    return {source["key"]: source["event"] for source in case["messages"]}


def replay(phase):
    results, failures = [], []
    v1 = json.loads(CASES.read_text(encoding="utf-8"))
    v2 = {value["id"]:value for value in json.loads(
        REFERENCE_V2.read_text(encoding="utf-8"))["scenes"]}
    for case in v1:
        record = json.loads((ROOT / "evidence/v03-stage-a-plus" / phase / f"{case['id']}.json")
                            .read_text(encoding="utf-8"))
        inputs = {value["memory_id"]: value for value in record["inputs"]}
        events = event_by_source(case)
        candidates = []
        for value in record["values"]:
            source = inputs[value["memory_id"]]
            judgment = assess_candidate(source)
            policy = release_decision(
                value, judgment, text_authorized=True, image_consent=True,
                egress_granted=True,
            )
            event = events[source["sources"][0]["message_id"]]
            candidates.append(dict(
                event=event, score=value["score"], p04_eligible=value["eligible"],
                p04_reason=value["reason_code"], local_judgment=judgment, policy=policy,
            ))
        eligible = [value for value in candidates
                    if value["policy"]["memorial_eligible"] and value["score"] >= .4]
        selected = max(eligible, key=lambda value: value["score"])["event"] if eligible else None
        acceptable = v2[case["id"]]["acceptable"]
        reasonable = selected in acceptable
        if not reasonable:
            failures.append(case["id"])
        results.append({
            "id": case["id"], "split": case["split"], "selected": selected,
            "acceptable": acceptable, "v1_acceptable": case["acceptable"],
            "reference_version": "v2-draft-pending-human", "reasonable": reasonable,
            "candidates": candidates,
        })
    return results, failures


def main():
    payload, summary = {}, {}
    for phase in PHASES:
        results, failures = replay(phase)
        payload[phase] = results
        summary[phase] = {
            "reasonable": sum(row["reasonable"] for row in results),
            "scenarios": len(results),
            "failures": failures,
            "s33": next(row for row in results if row["id"] == "S33"),
            "s18": next(row for row in results if row["id"] == "S18"),
            "s14_s16": [next(row for row in results if row["id"] == sid)
                        for sid in ("S14", "S15", "S16")],
        }
    output = {
        "mode": "OFFLINE_REPLAY_OF_IMMUTABLE_P04_OUTPUTS",
        "real_requests": 0, "image_requests": 0,
        "reference_version": "v2-draft-pending-human",
        "not_a_model_retest": True, "summary": summary, "details": payload,
    }
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT / "historical-contract-replay.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# A++ 对历史固定输出的合同回放", "",
        "不是新模型调用；只是将旧P04分数交给新分离合同，P04八维数值原样保留。", "",
        "| 阶段 | 合理选择 | S33 | S18 | S14–S16图像状态 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for phase, value in summary.items():
        s33 = next(c for c in value["s33"]["candidates"] if c["event"] == "grief")
        s18 = value["s18"]["candidates"][0]
        nonfacts = "、".join(
            f"{row['id']}:{row['candidates'][0]['local_judgment']['imageability']}"
            for row in value["s14_s16"]
        )
        lines.append(
            f"| {phase} | {value['reasonable']}/{value['scenarios']} | "
            f"{s33['policy']['storage_status']} / {s33['policy']['imageability']} | "
            f"{s18['policy']['storage_status']} / {s18['policy']['imageability']} | {nonfacts} |"
        )
    lines += [
        "", "失败场景保留供审查：" + (
            "、".join(sorted(set(summary['baseline']['failures'] + summary['retest']['failures'])))
            or "无"
        ),
        "", "限制：本地规则对S12的“第一次训练”等歧义不作自动裁决；"
        "正式语义质量仍需新的真实模型调用及真人复核。",
    ]
    (OUTPUT / "historical-contract-replay.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({phase: {k:v for k,v in value.items()
                              if k in ("reasonable","scenarios","failures")}
                      for phase,value in summary.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
