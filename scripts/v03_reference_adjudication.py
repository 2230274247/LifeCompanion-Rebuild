"""Prepare and validate human judgments; never fabricates a human reviewer."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "fixtures/recollection-policy-v2/reference-v2-draft.json"
TEMPLATE = ROOT / "evidence/v03-stage-a-plus-plus/human-adjudication.template.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def init():
    if TEMPLATE.exists():
        raise SystemExit("Human adjudication template already exists; refusing to overwrite.")
    draft = load(DRAFT)
    write(TEMPLATE, {
        "version": "human-adjudication-v1",
        "source_reference": str(DRAFT.relative_to(ROOT)),
        "source_reference_sha256": hashlib.sha256(DRAFT.read_bytes()).hexdigest(),
        "reviewer_type": "PENDING_HUMAN",
        "reviewer_id": "",
        "reviewed_at": "",
        "status": "PENDING",
        "scenes": [{
            "id": scene["id"], "decision": "PENDING",
            "acceptable": scene["acceptable"], "required": scene["required"],
            "ambiguity": scene["ambiguity"], "note": "",
        } for scene in draft["scenes"]],
    })
    print(f"Template created at {TEMPLATE}; it is not a completed review.")


def validate(path):
    value = load(path)
    draft = load(DRAFT)
    if value.get("reviewer_type") != "HUMAN" or not str(value.get("reviewer_id","")).strip():
        raise SystemExit("HUMAN_REVIEWER_REQUIRED")
    try:
        datetime.fromisoformat(value["reviewed_at"].replace("Z","+00:00"))
    except (KeyError,TypeError,ValueError) as exc:
        raise SystemExit("HUMAN_REVIEW_TIMESTAMP_REQUIRED") from exc
    expected = {scene["id"] for scene in draft["scenes"]}
    rows = value.get("scenes", [])
    if {row.get("id") for row in rows} != expected or len(rows) != len(expected):
        raise SystemExit("ALL_36_SCENES_REQUIRED")
    for row in rows:
        if row.get("decision") not in ("ACCEPT_DRAFT","AMEND","REJECT"):
            raise SystemExit(f"INVALID_ADJUDICATION:{row.get('id')}")
        if row["id"] == "S12":
            if not row.get("ambiguity") or not row.get("note", "").strip():
                raise SystemExit("S12_AMBIGUITY_NOTE_REQUIRED")
    value["status"] = "HUMAN_REVIEWED"
    value["verified_at"] = datetime.now().astimezone().isoformat()
    output = ROOT / "fixtures/recollection-policy-v2/reference-v2-reviewed.json"
    write(output, value)
    print(f"PASS: human review validated and written to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "validate"])
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    if args.action == "init":
        init()
    else:
        if not args.path:
            parser.error("validate requires a JSON path")
        validate(args.path)
