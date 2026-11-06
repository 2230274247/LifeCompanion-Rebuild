"""Offline integrity checks; prints counts, never configured secret values."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd).decode("utf-8-sig").strip()


checks = {}
checks["engineering"] = all(
    sha(Path(row["Path"])).upper() == row["Hash"].upper()
    for row in json.loads((HERE / "engineering-before.json").read_text(encoding="utf-8-sig"))
)
checks["p04_unchanged"] = (
    sha(ROOT / "services/life-core/app/recollection_scoring.py")
    == sha(HERE / "before/recollection_scoring.py")
)
checks["aggregation_unchanged"] = (
    sha(ROOT / "services/life-core/app/moment_semantics.py")
    == sha(HERE / "before/moment_semantics.py")
)
canonical = ROOT.parent.parent
snapshot = json.loads((ROOT / "evidence/v03-stage-a/canonical-before.json").read_text(encoding="utf-8-sig"))
checks["canonical_58_files"] = all(sha(canonical / name) == digest for name, digest in snapshot.items())
checks["nested_worktree_status"] = (
    git("status", "--short", cwd=ROOT / "products/librechat-custom")
    == (HERE / "librechat-before.txt").read_text(encoding="utf-8-sig").strip()
)
frozen = json.loads((HERE / "freeze-manifest.json").read_text(encoding="utf-8"))
checks["frozen_cases"] = sha(HERE / "frozen-cases.json") == frozen["cases_sha256"]
checks["frozen_rubric"] = sha(ROOT / "docs/product/V03_Aplus_语义评估口径.md") == frozen["rubric_sha256"]
with sqlite3.connect(HERE / "request-budget.sqlite3") as db:
    db.row_factory = sqlite3.Row
    rows = [dict(row) for row in db.execute("SELECT * FROM requests")]
checks["budget_108_no_resend"] = len(rows) == 108 and len({r["key"] for r in rows}) == 108
checks["all_http_200"] = all(r["http_status"] == 200 and r["status"] == "received" for r in rows)
checks["request_limits"] = all(
    r["input_bytes"] <= 26000 and json.loads(r["request_json"])["max_tokens"] <= 2048
    for r in rows
)
events = [(r["started"], 1) for r in rows] + [(r["completed"], -1) for r in rows]
active, peak = 0, 0
for _, delta in sorted(events):
    active += delta
    peak = max(peak, active)
checks["concurrency_at_most_3"] = peak <= 3 and active == 0
secrets = []
for line in (ROOT / "infra/runtime/p00/acceptance.env").read_text(encoding="utf-8-sig").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        name, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if any(part in name.upper() for part in ("KEY", "TOKEN", "PASSWORD", "SECRET")) and len(value) >= 12:
            secrets.append(value.encode("utf-8"))
scope = list(HERE.rglob("*"))
scope += [ROOT / "scripts" / name for name in (
    "v03_semantic_cases.py", "v03_semantic_eval.py", "report_v03_semantic_eval.py")]
scope += [ROOT / "services/life-core/tests/test_v03_semantic_eval.py",
          ROOT / "docs/product/V03_Aplus_语义评估口径.md",
          ROOT / "docs/product/README.md", ROOT / "docs/development-log/README.md"]
scope += list((ROOT / "docs/development-log").glob("*Aplus*开发验收.md"))
leaks = [str(path.relative_to(ROOT)) for path in scope
         if path.is_file() and any(secret in path.read_bytes() for secret in secrets)]
checks["configured_secrets_absent"] = not leaks
result = dict(status="PASS" if all(checks.values()) else "FAIL", checks=checks,
              canonical_files=len(snapshot), peak_requests=peak,
              request_count=len(rows), secret_scan_files=sum(p.is_file() for p in scope),
              secret_match_files=leaks,
              scope_note="Historical Stage A files were not written by this task; no pre-A+ full historical hash snapshot exists.")
(HERE / "integrity-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if result["status"] == "PASS" else 1)
