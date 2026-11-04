"""Reproducible Chinese A+ report from immutable real-response evidence."""
from __future__ import annotations

import html
import json
import sqlite3

from v03_semantic_eval import (
    CASES, EVIDENCE, WEIGHTS, dump, gate_axes, summarize,
)


def pct(numerator, denominator):
    return f"{numerator}/{denominator} ({numerator / denominator:.1%})" if denominator else "0/0 (N/A)"


def scene_label(value):
    return "跳过" if value is None else str(value)


def main():
    reports = {}
    for phase in ("baseline", "retest"):
        reports[phase] = {}
        for split in ("development", "holdout"):
            value = summarize(phase, split)
            reports[phase][split] = value
            dump(EVIDENCE / f"{phase}-{split}-summary.json", value)

    with sqlite3.connect(EVIDENCE / "request-budget.sqlite3") as db:
        db.row_factory = sqlite3.Row
        ledger = {row["key"]: dict(row) for row in db.execute("SELECT * FROM requests")}
    axis_totals = {}
    axis_details = {}
    for split in ("development", "holdout"):
        totals = dict(candidates=0, raw_class_correct=0, gated_class_correct=0,
                      memorial_correct=0, text_only=0, text_only_correct=0,
                      private=0, private_correct=0, ungrounded_visual_candidates=0,
                      gated_visual_candidates=0, remaining_unverified_visual_candidates=0,
                      raw_batch_errors=0, grounded_source_candidates=0)
        for case in [c for c in CASES if c["split"] == split]:
            result = json.loads((EVIDENCE / "axes" / f"{case['id']}.json").read_text(encoding="utf-8"))
            call = ledger.get(f"axes:{case['id']}", {})
            response = json.loads(call.get("response_json") or "{}")
            body = json.loads(response["choices"][0]["message"]["content"])
            raw_values = body["candidates"]
            grounded = gate_axes(body, result["inputs"])
            source_refs = {s["key"]: s for s in case["messages"]}
            input_map = {v["memory_id"]: v for v in result["inputs"]}
            raw_map = {v["memory_id"]: v for v in raw_values}
            details = []
            for value in grounded:
                item = input_map[value["memory_id"]]
                reference = source_refs[item["sources"][0]["message_id"]]
                raw = raw_map[value["memory_id"]]
                event = reference["event"]
                quotes = [s["quote"] for s in item["sources"]]
                raw_unverified = any(not fact.strip() or not any(
                    fact in quote for quote in quotes
                ) for fact in raw["visual_facts"])
                gated_unverified = any(not any(fact in quote for quote in quotes)
                                       for fact in value["visual_facts"])
                if event in case["required"]:
                    allowed_memorial = ["KEEP"]
                elif reference["privacy"] == "sensitive" or event in case["acceptable"]:
                    allowed_memorial = ["KEEP", "SKIP"]
                else:
                    allowed_memorial = ["SKIP"]
                totals["candidates"] += 1
                totals["raw_class_correct"] += raw["imageability"] == reference["image"]
                totals["gated_class_correct"] += value["imageability"] == reference["image"]
                totals["memorial_correct"] += value["memorial"] in allowed_memorial
                totals["text_only"] += reference["image"] == "TEXT_ONLY"
                totals["text_only_correct"] += (
                    reference["image"] == "TEXT_ONLY" and value["imageability"] == "TEXT_ONLY"
                )
                totals["private"] += reference["image"] == "PRIVATE_SKIP"
                totals["private_correct"] += (
                    reference["image"] == "PRIVATE_SKIP" and value["imageability"] == "PRIVATE_SKIP"
                )
                totals["ungrounded_visual_candidates"] += raw_unverified
                totals["gated_visual_candidates"] += value["gate_reason"] is not None
                totals["remaining_unverified_visual_candidates"] += gated_unverified
                totals["grounded_source_candidates"] += value["gate_reason"] != "UNGROUNDED_SOURCE"
                details.append(dict(event=event, expected_image=reference["image"],
                                    allowed_memorial=allowed_memorial, raw=raw, gated=value,
                                    quotes=item["sources"]))
            totals["raw_batch_errors"] += result["error"] is not None
            axis_details[case["id"]] = dict(error=result["error"], candidates=details)
        axis_totals[split] = totals

    usage = dict(
        requests=len(ledger), max_requests=108,
        requests_with_response=sum(r["status"] == "received" for r in ledger.values()),
        input_tokens=sum(r["input_tokens"] or 0 for r in ledger.values()),
        output_tokens=sum(r["output_tokens"] or 0 for r in ledger.values()),
        mode="REAL_DEEPSEEK", image_requests=0, currency_cost="UNKNOWN",
        response_ids={key: value["request_id"] for key, value in ledger.items()},
        http_errors={key: value["http_status"] for key, value in ledger.items()
                     if value["http_status"] != 200},
    )
    checks = {}
    for split in ("development", "holdout"):
        t = reports["retest"][split]["totals"]
        a = axis_totals[split]
        checks[split] = dict(
            reasonable=t["reasonable"] / t["scenarios"] >= .9,
            false_exclusion=t["false_exclusions"] / max(t["required"], 1) <= .1,
            merge=t["false_merges"] == 0,
            sources=t["authentic"] == t["expected"],
            privacy=t["private_selected"] == 0 and t["private_eligible"] == 0,
            image_classification=a["gated_class_correct"] / a["candidates"] >= .95,
        )
    passed = all(all(v.values()) for v in checks.values())
    payload = dict(reports=reports, axes=dict(totals=axis_totals, details=axis_details),
                   usage=usage, checks=checks, statistical_gate="PASS" if passed else "PARTIAL",
                   human_reference_review="NOT TESTED", stage_b="NOT AUTHORIZED")
    dump(EVIDENCE / "comparison.json", payload)

    lines = [
        "# V0.3 A+ 真实语义选择质量评估报告",
        "",
        "**结论：统计门为 " + payload["statistical_gate"] +
        "；真人参考复核 NOT TESTED；本轮不进入阶段 B。**",
        "",
        "36 个冻结合成场景，24 开发、12 留出。参考答案由代理依据产品定位拟定，"
        "尚未经过真人标注/签署，不能冒称人工金标准或真实用户准确率。"
        "多个合理候选均接受，低排名但合格不计为误排除。",
        "",
        "阶段 A 的 P04 八维权重、Prompt 和工程代码保持原样。基线开发集没有明确语义失败，"
        "因此不做无依据调参；复测是独立真实请求对原模型输出稳定性的验证。"
        "唯一改动是离线两轴评估的逐候选证据门，无法逐字核验的视觉短语退回仅文字，"
        "不影响纪念价值，不发送图片、不改变原聊天。",
        "",
        "本评估直接提供合成候选、执行真实阶段 A 聚合及真实 P04 云调用；"
        "不代表聊天抽取/授权数据库端到端验收。私密场景也是虚构文本，没有真实病历或地址。",
        "",
        "## 前后指标",
        "",
        "| 阶段/集合 | 选择合理率 | 误排除率 | 误合并率 | 漏合并率 | 来源真实性 | 隐私候选选中/准入 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for phase in ("baseline", "retest"):
        for split in ("development", "holdout"):
            t = reports[phase][split]["totals"]
            lines.append(
                f"| {phase}/{split} | {pct(t['reasonable'], t['scenarios'])} | "
                f"{pct(t['false_exclusions'], t['required'])} | "
                f"{pct(t['false_merges'], t['independent_pairs'])} | "
                f"{pct(t['missed_merges'], t['same_event_pairs'])} | "
                f"{pct(t['authentic'], t['returned'])}，返回{t['returned']}/{t['expected']} | "
                f"{t['private_selected']}/{t['private_events']}；准入{t['private_eligible']} |"
            )
    lines += [
        "", "## 独立纪念价值与图像适用性", "",
        "| 集合 | 纪念价值一致 | 图像类别原始一致 | 证据门后类别一致 | 仅文字识别 | 隐私识别 | 无法逐字核验视觉事实（前→后） |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for split, a in axis_totals.items():
        lines.append(
            f"| {split} | {pct(a['memorial_correct'],a['candidates'])} | "
            f"{pct(a['raw_class_correct'],a['candidates'])} | "
            f"{pct(a['gated_class_correct'],a['candidates'])} | "
            f"{pct(a['text_only_correct'],a['text_only'])} | "
            f"{pct(a['private_correct'],a['private'])} | "
            f"{a['ungrounded_visual_candidates']}→{a['remaining_unverified_visual_candidates']} |"
        )
    lines += [
        "",
        "原始类别正确并不代表视觉事实可用。证据门把未逐字核验的SAFE_SCENE退为TEXT_ONLY，"
        "可以减少画面通过量并降低类别召回率；这种退回如实计为相对参考的误拒，不能隐去。"
        "不能逐字回指可能只是模型改写，并不等同事实性幻觉。原始输出、错误、降级理由全部保留。",
        "",
        "## 目标起步与复述对照", "",
    ]
    for phase in ("baseline", "retest"):
        detail = reports[phase]["development"]["details"]
        for sid in ("S02", "S03", "S11", "S23"):
            r = detail[sid]
            data = [(v["event"], v["score"], v["eligible"], v["dimensions"]["personal_meaning"],
                     v["dimensions"]["source_sufficiency"]) for v in r["values"]]
            lines.append(f"- {phase} {sid}：选择{scene_label(r['selected'])}；"
                         f"(事件,总分,合格,个人意义,来源充足)={data}。")
    lines += [
        "",
        "## 误选原因与合理分歧", "",
    ]
    failures = []
    for phase in ("baseline", "retest"):
        for split in ("development", "holdout"):
            for sid, d in reports[phase][split]["details"].items():
                if not d["reasonable"] or d["false_exclusions"]:
                    failures.append(f"- {phase} {sid}：选中{scene_label(d['selected'])}；"
                                    f"误排除{d['false_exclusions']}；原因见逐候选八维与理由。")
    lines += failures or ["- P04 两次请求中未发现参考明确不接受的选择或必须候选的错误排除。"
                          "这只适用于本合成集，不能外推。"]
    lines += [
        "- S33（留出，基线及复测）：用户明确希望把对逝去亲人的思念及内在进展留下文字；"
        "P04个人意义均为0.90，却因隐私适用性低而被硬门排除。独立纪念轴判断KEEP、"
        "图像轴TEXT_ONLY。这是文字纪念价值与图片外发资格耦合的明确问题，"
        "不应通过放松隐私保护来修复；需后续把文字保留与生图准入分开验收。",
        "- S12（开发，复测）：第一次训练0.650高于完成双次训练目标0.646，冻结参考仅接受第二次。"
        "但“这是第一次训练”可能被理解为人生首次，存在参考语义歧义。"
        "保留冻结错选计数，不事后改标签美化结果，待真人裁决；不能直接认定模型明显错误。",
        "- 两次P04使用完全相同的权重与Prompt；合理率变化是独立请求的输出波动，"
        "不是调参改进效果。两轴证据门的前后比较来自同一份原始响应，属于离线处理对照。",
        "- 图像类别分歧包含安全的保守退回：有具体事实的日常、回忆录完成或散步里程碑"
        "被判TEXT_ONLY；另有未来计划/AI建议/不确定事件被判PRIVATE_SKIP。"
        "应分别复核事实充分性与类别定义，不能把这些分歧全部称为幻觉或隐私泄漏。",
    ]
    for split in ("development", "holdout"):
        for sid, d in reports["retest"][split]["details"].items():
            if d["reasonable_disagreement"]:
                lines.append(f"- {sid}：{scene_label(d['selected'])}落入多合理候选集合，记合理分歧，"
                             "不强制唯一排名。")
    for sid, a in axis_details.items():
        for item in a["candidates"]:
            raw, gated = item["raw"], item["gated"]
            if gated["gate_reason"] or gated["imageability"] != item["expected_image"]:
                lines.append(
                    f"- 两轴 {sid}/{item['event']}：参考{item['expected_image']}，"
                    f"原始{raw['imageability']}→证据门{gated['imageability']}，"
                    f"{gated['gate_reason'] or 'MODEL_CLASS_DISAGREEMENT'}；"
                    f"原原因：{raw['image_reason']}。"
                )
    lines += [
        "", "## 预算与证据", "",
        f"- 真实调用 {usage['requests']}/108；已返回{usage['requests_with_response']}；"
        f"输入{usage['input_tokens']}、输出{usage['output_tokens']} tokens。",
        "- 原始请求/响应、响应ID、HTTP状态、usage及先预留账本：request-budget.sqlite3；"
        "字段不含Authorization或凭据。外发路径仅api.deepseek.com/v1/chat/completions。",
        "- 自动重试0；生图/Kolors调用0；真实用户数据写入0；金额UNKNOWN。",
        "- baseline/、retest/、axes/逐场景JSON；frozen-cases.json与freeze-manifest.json记录冻结内容。",
        "- 全部维度、最终硬门理由、模型理由、原始quote和逐候选两轴原因见comparison.json。",
        "",
        "## 局限与阶段门", "",
        "- 参考为待真人复核草案；留出由同一代理撰写，且大多明确表达纪念意愿，"
        "偏简单、样本小、不是独立真实用户盲测。",
        "- 留出模型输出在decision-before-holdout.json锁定后才用于分析，未据其调整实现。"
        "temperature=0仍可能变化，复测不等于严格重复性保证。",
        "- 预设门：两集合选择合理率>=90%、误排除<=10%、误合并0%、来源100%、"
        "隐私未准入且未入选，图像类别>=95%。逐门检查见comparison.json/checks。",
        "- 证据门可正确阻止不可核验画面，但SAFE_SCENE被保守降为TEXT_ONLY的召回损失仍需解决；"
        "未将其称为生成系统已交付。",
        "- 即使统计门通过，也需要用户复核拟定标准；本轮没有进入B，保留全部阶段A历史证据。",
        "",
        "## 逐场景前后评分与来源", "",
    ]
    cards = []
    for case in CASES:
        sid, split = case["id"], case["split"]
        b = reports["baseline"][split]["details"][sid]
        r = reports["retest"][split]["details"][sid]
        axes = axis_details[sid]
        lines += [
            f"### {sid} {case['category']}（{split}）", "",
            "参考可接受：" + "、".join(scene_label(v) for v in case["acceptable"]) +
            "；必须可保留：" + ("、".join(case["required"]) or "无") + "。",
            "", case["rationale"], "",
            f"基线选择：{scene_label(b['selected'])}；复测选择：{scene_label(r['selected'])}。",
            "",
        ]
        rows = []
        for phase, detail in (("baseline", b), ("retest", r)):
            for v in detail["values"]:
                dimensions = "；".join(f"{name}={v['dimensions'][name]:.2f}" for name in WEIGHTS)
                lines.append(
                    f"- {phase} {v['event']}：{v['score']:.4f}，合格={v['eligible']}，"
                    f"硬门理由={v['reason_code']}，模型理由={v['model_reason_code']}；{dimensions}。"
                )
                lines.append(
                    f"  引用消息={v['source_message_ids']}；逐字证据：{v['evidence_quote']}。"
                )
                rows.append(
                    "<tr><td>" + html.escape(phase) + "</td><td>" + html.escape(v["event"]) +
                    f"</td><td>{v['score']:.4f}</td><td>{v['eligible']}</td><td>" +
                    html.escape(v["reason_code"]) + "</td><td>" + html.escape(dimensions) + "</td></tr>"
                )
        lines += [""]
        source_html = []
        for source in case["messages"]:
            lines.append(f"- 来源 `{source['key']}` / 事件 `{source['event']}`：{source['text']}")
            source_html.append(f"<li><code>{source['key']}</code> {html.escape(source['text'])}</li>")
        axis_html = []
        for item in axes["candidates"]:
            v = item["gated"]
            text = (
                f"{item['event']}：纪念={v['memorial']}（{v['memorial_reason']}）；"
                f"图像={item['raw']['imageability']}→{v['imageability']}（{v['image_reason']}）；"
                f"证据门={v['gate_reason'] or 'PASS'}"
            )
            lines.append("- 独立两轴 " + text)
            axis_html.append("<p>" + html.escape(text) + "</p>")
        lines.append("")
        cards.append(
            f'<article data-split="{split}" data-search="{html.escape(sid + case["category"],quote=True)}">'
            f"<h2>{sid} · {html.escape(case['category'])}</h2>"
            f"<p>参考：{html.escape(str(case['acceptable']))} · "
            f"基线{scene_label(b['selected'])} → 复测{scene_label(r['selected'])}</p>"
            f"<p>{html.escape(case['rationale'])}</p><ul>{''.join(source_html)}</ul>"
            f'<div class="scroll"><table><thead><tr><th>阶段</th><th>事件</th><th>总分</th>'
            f"<th>合格</th><th>理由</th><th>八维</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
            + "".join(axis_html) + "</article>"
        )
    report_path = EVIDENCE / "中文评估报告.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    summary_cards = []
    for phase in ("baseline", "retest"):
        for split in ("development", "holdout"):
            t = reports[phase][split]["totals"]
            summary_cards.append(
                f"<div><small>{phase} / {split}</small><strong>"
                f"{pct(t['reasonable'],t['scenarios'])}</strong><span>选择合理率</span></div>"
            )
    document = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LifeCompanion A+ 真实语义评估</title>
<style>
:root{--paper:#f5f2e9;--ink:#173a34;--accent:#b34f30;--line:#bbc5b9}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(at 90% 0,#c8dfd0,transparent 40%),var(--paper);
color:var(--ink);font:16px/1.65 Georgia,"Noto Serif SC",serif}main{max-width:1300px;margin:auto;padding:40px 24px}
h1{font-size:clamp(30px,5vw,60px);line-height:1.12}h2{font-size:24px}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.summary div{border-top:3px solid var(--ink);padding:14px}
.summary strong,.summary span{display:block}.summary strong{font-size:22px}
.notice{border-left:5px solid var(--accent);padding:14px;background:#fff8ed}
nav{display:flex;gap:12px;flex-wrap:wrap;margin:28px 0}input,select{padding:12px;max-width:100%;font:inherit}
article{background:#fffdf6;border:1px solid var(--line);padding:22px;margin:24px 0;overflow-wrap:anywhere}
.scroll{overflow:auto}table{border-collapse:collapse;min-width:760px;width:100%;font:13px/1.7 Consolas,monospace}
td,th{text-align:left;border-bottom:1px solid var(--line);padding:8px;vertical-align:top}
td:not(:last-child),th{white-space:nowrap}td:last-child{min-width:280px}
code{font-family:Consolas,monospace}small{font-size:13px}
@media(max-width:700px){.summary{grid-template-columns:1fr 1fr}main{padding:20px 14px}article{padding:14px}}
</style><main><small>V0.3 A+ · REAL DEEPSEEK · SYNTHETIC DATA</small>
<h1>什么值得记住，什么适合成图</h1>
<p class="notice">36个冻结合成场景 · 参考由代理拟定、待真人复核。评分是真实API；生图调用0。
P04八维权重与Prompt未修改；不以跑步必须胜过读书为目标。</p>
<section class="summary">""" + "".join(summary_cards) + f"""</section>
<p>统计门：{payload['statistical_gate']} · 真人参考复核：NOT TESTED · 本轮不进入阶段B。
两轴失败与仅文字降级完整保留，不能因卡片数量补造事实。</p>
<nav><label>集合 <select id="split"><option value="all">全部</option><option value="development">开发24场景</option>
<option value="holdout">留出12场景</option></select></label><label>筛选 <input id="search" placeholder="S03 / 复述 / 隐私"></label></nav>
<div id="scenes">""" + "".join(cards) + """</div></main>
<script>
function filter(){const s=document.querySelector('#split').value,q=document.querySelector('#search').value.toLowerCase();
document.querySelectorAll('article').forEach(a=>a.hidden=!(s==='all'||a.dataset.split===s)||!a.textContent.toLowerCase().includes(q));}
document.querySelector('#split').addEventListener('change',filter);document.querySelector('#search').addEventListener('input',filter);
</script></html>"""
    (EVIDENCE / "review.html").write_text(document, encoding="utf-8")
    print(json.dumps(dict(usage={k:v for k,v in usage.items() if k != "response_ids"},
                          checks=checks, axes=axis_totals,
                          statistics={p:{s:v["totals"] for s,v in r.items()} for p,r in reports.items()}),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
