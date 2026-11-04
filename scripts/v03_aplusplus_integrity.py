"""Produce the A++ integrity manifest without printing configured secret values."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/v03-stage-a-plus-plus"
BEFORE = EVIDENCE / "before"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


history = load(EVIDENCE / "history-before.json")
holdout = load(EVIDENCE / "holdout-results.json")
historical = load(EVIDENCE / "historical-contract-replay.json")
reference = load(ROOT / "fixtures/recollection-policy-v2/reference-v2-draft.json")
holdout_fixture = load(ROOT / "fixtures/recollection-policy-v2/holdout.json")
reference_freeze = load(EVIDENCE / "reference-freeze.json")

with sqlite3.connect(ROOT / "evidence/v03-stage-a-plus/request-budget.sqlite3") as db:
    request_rows = db.execute("SELECT key,status,http_status FROM requests").fetchall()

checks = {
    "pre_aplusplus_evidence_374_unchanged": (
        len(history) == 374
        and all(
            (ROOT / relative).is_file() and digest(ROOT / relative) == expected
            for relative, expected in history.items()
        )
    ),
    "p04_scoring_unchanged": (
        digest(ROOT / "services/life-core/app/recollection_scoring.py")
        == digest(BEFORE / "services/life-core/app/recollection_scoring.py")
    ),
    "window_logic_unchanged": (
        digest(ROOT / "services/life-core/app/moment_windows.py")
        == digest(BEFORE / "services/life-core/app/moment_windows.py")
    ),
    "semantic_aggregation_unchanged": (
        digest(ROOT / "services/life-core/app/moment_semantics.py")
        == digest(BEFORE / "services/life-core/app/moment_semantics.py")
    ),
    "aplus_ledger_still_108_unique_received": (
        len(request_rows) == 108
        and len({row[0] for row in request_rows}) == 108
        and all(row[1] == "received" and row[2] == 200 for row in request_rows)
    ),
    "aplusplus_real_requests_zero": (
        holdout["real_requests"] == 0 and historical["real_requests"] == 0
    ),
    "aplusplus_image_requests_zero": (
        holdout["image_requests"] == 0 and historical["image_requests"] == 0
    ),
    "holdout_offline_contract_pass": holdout["status"] == "PASS",
    "holdout_not_model_or_human_evidence": (
        holdout["model_evidence"] is False
        and holdout["human_reviewed"] is False
        and holdout["contract"] == "OFFLINE_LOCAL_JUDGMENT_ONLY"
    ),
    "historical_replay_not_model_retest": historical["not_a_model_retest"] is True,
    "original_36_references_preserved": len(reference["scenes"]) == 36,
    "new_holdout_20_preserved": len(holdout_fixture["scenes"]) == 20,
    "human_review_still_pending": reference["status"] == "PENDING_HUMAN_REVIEW",
    "s12_ambiguity_flagged": next(
        scene for scene in reference["scenes"] if scene["id"] == "S12"
    )["ambiguity"] is not None,
    "reference_freeze_hashes_match": all(
        digest(ROOT / relative) == expected
        for relative, expected in reference_freeze["files"].items()
    ),
    "image_generation_default_off": (
        'LIFE_MOMENT_IMAGE_GENERATION_ENABLED=false'
        in (ROOT / ".env.example").read_text(encoding="utf-8-sig")
        and 'LIFE_MOMENT_IMAGE_PROVIDER=\n'
        in (ROOT / ".env.example").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    ),
}

secrets = []
for line in (ROOT / "infra/runtime/p00/acceptance.env").read_text(
    encoding="utf-8-sig"
).splitlines():
    if "=" not in line or line.lstrip().startswith("#"):
        continue
    name, value = line.split("=", 1)
    value = value.strip().strip('"').strip("'")
    if (
        any(part in name.upper() for part in ("KEY", "TOKEN", "PASSWORD", "SECRET"))
        and len(value) >= 12
    ):
        secrets.append(value.encode("utf-8"))

scope = [
    path for path in EVIDENCE.rglob("*")
    if path.is_file() and path.name not in ("integrity-manifest.json", "integrity-run.log")
]
scope += [path for path in (ROOT / "fixtures/recollection-policy-v2").rglob("*") if path.is_file()]
scope += [
    ROOT / ".env.example",
    ROOT / "services/life-core/app/recollection_policy.py",
    ROOT / "services/life-core/app/moments.py",
    ROOT / "services/life-core/app/main.py",
    ROOT / "services/life-core/app/config.py",
    ROOT / "services/life-core/tests/test_recollection_policy.py",
    ROOT / "services/life-core/tests/test_recollection_separation.py",
    ROOT / "services/life-core/tests/test_recollection_authorization.py",
    ROOT / "services/life-core/tests/test_v03_selection.py",
    ROOT / "services/life-core/tests/test_v03_recovery.py",
    ROOT / "products/librechat-custom/client/src/components/Life/Moments.tsx",
    ROOT / "products/librechat-custom/client/src/components/Life/__tests__/Memories.spec.tsx",
    ROOT / "products/librechat-custom/client/src/locales/en/translation.json",
    ROOT / "products/librechat-custom/packages/data-provider/src/life.ts",
    ROOT / "docs/architecture/V03_Aplusplus_RECOLLECTION_SEPARATION.md",
    ROOT / "docs/architecture/README.md",
    ROOT / "docs/product/README.md",
    ROOT / "docs/development-log/README.md",
    ROOT / "docs/development-log/2026-11-04_14-20_V03Aplusplus纪念价值图像资格与授权解耦_开发验收.md",
]
scope += sorted((ROOT / "scripts").glob("v03_aplusplus_*.py"))
scope += sorted((ROOT / "scripts").glob("v03_reference_adjudication.py"))
leaks = [
    str(path.relative_to(ROOT))
    for path in scope
    if path.is_file() and any(secret in path.read_bytes() for secret in secrets)
]
checks["configured_secrets_absent_from_aplusplus_scope"] = not leaks

manifest_files = sorted({str(path.relative_to(ROOT)) for path in scope if path.is_file()})
status = "PASS" if all(checks.values()) else "FAIL"
result = {
    "status": status,
    "scope": "V0.3 A++ engineering integrity only; not semantic or human acceptance",
    "manifest_excludes": ["evidence/v03-stage-a-plus-plus/integrity-manifest.json",
                          "evidence/v03-stage-a-plus-plus/integrity-run.log"],
    "checks": checks,
    "pre_aplusplus_evidence_files": len(history),
    "aplus_ledger_requests": len(request_rows),
    "aplusplus_real_requests": holdout["real_requests"] + historical["real_requests"],
    "aplusplus_image_requests": holdout["image_requests"] + historical["image_requests"],
    "reference_scenarios": len(reference["scenes"]),
    "holdout_scenarios": len(holdout_fixture["scenes"]),
    "secret_scan_files": len(manifest_files),
    "secret_match_files": leaks,
    "files": {relative: digest(ROOT / relative) for relative in manifest_files},
}
(EVIDENCE / "integrity-manifest.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({key: result[key] for key in (
    "status", "checks", "pre_aplusplus_evidence_files", "aplus_ledger_requests",
    "aplusplus_real_requests", "aplusplus_image_requests", "reference_scenarios",
    "holdout_scenarios", "secret_scan_files", "secret_match_files",
)}, ensure_ascii=False, indent=2))
raise SystemExit(0 if status == "PASS" else 1)
