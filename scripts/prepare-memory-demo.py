"""Add synthetic history through the existing P5 account's authenticated user API.

No direct database writes, service credentials, password changes or invented chat
responses. Manual extraction uses the existing offline extractor; these fixtures
do not count as real DeepSeek extraction acceptance. Credentials stay in their
existing gitignored account file and are never copied into reports.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/p5"
NS = uuid.UUID("1f3ec35a-4dbe-4450-867e-de08a35374df")


def dataset():
    # All names and experiences are fictional test fixtures.
    places = ["苏州博物馆", "南京明城墙", "杭州西湖", "上海自然博物馆", "扬州瘦西湖", "无锡鼋头渚", "宁波天一阁", "绍兴鲁迅故里", "湖州南浔古镇", "嘉兴南湖", "镇江金山寺", "杭州龙井村"]
    dishes = ["番茄炒蛋", "香菇鸡汤", "清蒸鲈鱼", "南瓜粥", "红烧豆腐", "春笋炒肉", "凉拌黄瓜", "冬瓜虾仁汤", "玉米排骨汤", "莲藕炖肉", "山药小米粥", "栗子烧鸡"]
    books = ["《小王子》", "《活着》", "《围城》", "《朝花夕拾》", "《城南旧事》", "《瓦尔登湖》", "《人间草木》", "《平凡的世界》", "《边城》", "《老人与海》", "《昆虫记》", "《苏东坡传》"]
    skills = ["手机摄影构图", "毛笔楷书", "水彩静物", "八段锦", "口琴入门", "陶艺拉坯", "盆景修剪", "剪纸", "尤克里里", "篆刻", "中国结", "手冲咖啡"]
    songs = ["茉莉花", "送别", "月亮代表我的心", "小城故事", "春之歌", "外婆的澎湖湾", "童年", "让我们荡起双桨", "我和我的祖国", "红蜻蜓", "橄榄树", "故乡的云"]
    rows = []
    for month_index in range(12):
        total = 2025 * 12 + 10 + month_index
        year, zero_month = divmod(total, 12)
        month = zero_month + 1
        activities = [
            ("出游", f"我和朋友林晓参观了{places[month_index]}并拍了建筑和沿途风景。"),
            ("家常菜", f"我在家完成了{dishes[month_index]}的烹饪练习并把做法记在蓝色菜谱本里。"),
            ("读书", f"我参加了社区读书会并分享了{books[month_index]}中人物的选择。"),
            ("学习", f"我在社区文化中心完成了{skills[month_index]}课程的第一份练习并得到陈老师指导。"),
            ("运动", "我和朋友周宁在滨江步道完成了五公里步行并在终点一起喝了温水。"),
            ("音乐", f"我在社区合唱团排练了《{songs[month_index]}》的低声部并与大家合照留念。"),
            ("园艺", f"我在阳台给第{month_index + 1}盆薄荷换了土并把陶土花盆放在东侧窗边。"),
            ("家庭", f"我和家人整理了第{month_index + 1}本老照片册并挑选三张照片放进客厅相框。"),
            ("志愿服务", "我到社区图书室参加了两小时志愿服务并和王阿姨把儿童绘本按适读年龄分架。"),
            ("手工", f"我参加了社区手工集市并展示第{month_index + 1}幅自制明信片后向公益书箱捐了二十元。"),
        ]
        for index, (theme, activity) in enumerate(activities):
            date = f"{year:04d}-{month:02d}-{2 + index * 2:02d}"
            # Keep explicit date and activity in one source clause.
            text = date + activity.rstrip("。") + "（合成验收历史，非真实个人经历）。"
            rows.append({"key": f"demo-v2:{date}:{theme}", "date": date, "theme": theme,
                         "text": text, "month": date[:7], "synthetic": True})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=120, choices=range(1, 121))
    args = parser.parse_args()
    account = json.loads((RUNTIME / "lc-account.json").read_text(encoding="utf-8-sig"))
    token = ""

    def call(method, path, body=None, *, core=False):
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 Chrome/126.0.0.0"}
        if token:
            headers["Authorization"] = "Bearer " + token
        origin = "http://127.0.0.1:8010" if core else "http://127.0.0.1:3001"
        request = urllib.request.Request(origin + path, method=method, headers=headers,
            data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP_{exc.code} {method} {path}") from None

    login = call("POST", "/api/auth/login", {"email": account["email"], "password": account["password"]})
    token = login["token"]
    me = call("GET", "/life-api/api/v1/me")
    if me["librechat_user_id"] != account["id"] or login["user"]["id"] != account["id"]:
        raise RuntimeError("ACCOUNT_MAPPING_MISMATCH")
    before = call("GET", "/life-api/api/v1/memories?page_size=1")["total"]
    rows = dataset()[:args.limit]
    report = {"status": "PARTIAL", "mode": "authenticated manual API with offline extraction, not LLM extraction",
              "requested": len(rows), "before_total": before, "published": 0, "rows": [], "failures": []}

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for row in rows:
        source = str(uuid.uuid5(NS, account["id"] + ":" + row["key"]))
        try:
            result = call("POST", "/api/v1/events/extract", {"text": row["text"], "source_message_id": source,
                "occurred_at": row["date"] + "T18:00:00+08:00"}, core=True)
            events = [r["event"] for r in result.get("results", []) if r.get("accepted") and r.get("event")]
            if not events and result.get("event"):
                events = [result["event"]]
            if not events:
                raise RuntimeError("NO_PUBLISHED_EVENT")
            for event in events:
                if event["status"] != "published" or not event["memo_ref"]:
                    raise RuntimeError("PUBLICATION_NOT_CONFIRMED")
                if event["occurrence_start"] != row["date"] or event["occurrence_precision"] != "day":
                    raise RuntimeError("OCCURRENCE_NOT_CONFIRMED")
                detail = call("GET", "/life-api/api/v1/memories/" + event["event_id"])["memory"]
                if not detail["content"] or "合成验收历史" not in detail["content"]:
                    raise RuntimeError("SYNTHETIC_CONTENT_NOT_CONFIRMED")
                report["rows"].append({**row, "source_message_id": source,
                    "event_id": event["event_id"], "memo_ref": event["memo_ref"]})
                report["published"] += 1
        except Exception as exc:
            report["failures"].append({"key": row["key"], "reason": type(exc).__name__ + ": " + str(exc)})
        save()
        if (len(report["rows"]) + len(report["failures"])) % 20 == 0:
            print(f"Published {report['published']}; failed {len(report['failures'])}", flush=True)
    report["after_total"] = call("GET", "/life-api/api/v1/memories?page_size=1")["total"]
    report["status"] = "PASS" if report["published"] == len(rows) and not report["failures"] else "PARTIAL"
    save()
    print(f"{report['status']}: published={report['published']}, total={report['after_total']}", flush=True)


if __name__ == "__main__":
    main()
