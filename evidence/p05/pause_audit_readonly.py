"""Read-only closeout checks. Never contact an external API or initialize a store."""
import collections
import hashlib
import json
import re
import sqlite3
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def command(args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True, encoding="utf-8").rstrip("\r\n")


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def database(path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def write_json(name, data):
    (ROOT / "evidence/p05" / name).write_text(
        json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )


def dotenv(path):
    return dict(
        line.split("=", 1) for line in path.read_text(encoding="utf-8-sig").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )


def main():
    identity = json.loads(command(["python", "scripts/verify_rebuild_workspace.py"]))
    now = datetime.now().astimezone().isoformat()
    git = {
        "identity": identity,
        "root_status_porcelain": command(["git", "-c", "core.quotepath=false", "status", "--porcelain=v1", "-uall"]).splitlines(),
        "root_worktrees": command(["git", "worktree", "list", "--porcelain"]).splitlines(),
        "root_diff_stat": command(["git", "diff", "--stat"]).splitlines(),
        "nested_head": command(["git", "rev-parse", "HEAD"], ROOT / "products/librechat-custom"),
        "nested_status_porcelain": command(["git", "-c", "core.quotepath=false", "status", "--porcelain=v1", "-uall"], ROOT / "products/librechat-custom").splitlines(),
        "nested_branch": command(["git", "branch", "--show-current"], ROOT / "products/librechat-custom"),
        "checked_at": now,
        "note": "Includes inherited dirty files; not all changes belong to weather closeout. No commit/push/merge.",
    }
    for prefix in ("root", "nested"):
        lines = git[prefix + "_status_porcelain"]
        git[prefix + "_dirty_count"] = len(lines)
        git[prefix + "_untracked_count"] = sum(line.startswith("??") for line in lines)
    write_json("pause-git-status.json", git)

    usage_dbs, unique = [], {}
    checked_databases = 0
    for phase in ("p00", "p02", "p04", "p05"):
        for path in (ROOT / "infra/runtime" / phase).rglob("*.sqlite3"):
            if any(part in ("venv", "neo4j") for part in path.parts):
                continue
            checked_databases += 1
            with database(path) as db:
                for table, key in (("memory_model_calls", "call_id"), ("recollection_model_calls", "window_id")):
                    columns = [row[1] for row in db.execute("PRAGMA table_info(" + table + ")")]
                    if not columns:
                        continue
                    rows = [dict(row) for row in db.execute(
                        "SELECT " + key + ",model,status,input_tokens,output_tokens FROM " + table)]
                    if rows:
                        usage_dbs.append({
                            "database": str(path.relative_to(ROOT)), "table": table, "rows": len(rows),
                            "input_tokens": sum(row["input_tokens"] or 0 for row in rows),
                            "output_tokens": sum(row["output_tokens"] or 0 for row in rows),
                        })
                    for row in rows:
                        row_key = (table, row[key])
                        if row_key in unique:
                            assert unique[row_key] == row, "Copied ledger records diverge"
                        unique[row_key] = row
    usage = collections.defaultdict(lambda: {"rows": 0, "input_tokens": 0, "output_tokens": 0, "missing_usage": 0})
    for row in unique.values():
        summary = usage[row["model"] + " / " + row["status"]]
        summary["rows"] += 1
        summary["input_tokens"] += row["input_tokens"] or 0
        summary["output_tokens"] += row["output_tokens"] or 0
        summary["missing_usage"] += int(row["input_tokens"] is None or row["output_tokens"] is None)
    costs = {
        "checked_at": now, "external_requests_in_this_audit": 0,
        "sqlite_databases_checked": checked_databases, "databases_with_usage": usage_dbs,
        "deduplicated_by": "table + call_id/window_id; P04 browser copies counted once",
        "unique_ledger_rows": dict(usage),
        "historical_zhipu_chat_lower_bound": 5,
        "historical_zhipu_chat_sources": ["docs/product/p00-p07/P00/P00_STAGE_LOG.md", "docs/product/p00-p07/P01/P01_STAGE_LOG.md"],
        "historical_zhipu_extraction": "Real P02 baseline exists; complete request/token billing not captured",
        "historical_balance_observation": read_json("evidence/p02/deepseek-usage-summary.json"),
        "currency_cost_and_current_remaining_balance": "UNKNOWN; no fresh external balance query",
        "image_generation_calls_in_audited_P00_P05_evidence": 0,
        "scope": "Rebuild retained evidence/ledgers, not a provider-wide account billing statement",
    }

    path = ROOT / "infra/runtime/p05/tools-acceptance.sqlite3"
    with database(path) as db:
        integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        ledger = {
            "database": str(path.relative_to(ROOT)), "quick_check": integrity,
            "network_requests": db.execute("SELECT coalesce(sum(network_requests),0) FROM tool_executions").fetchone()[0],
            "statuses": [list(row) for row in db.execute("SELECT status,count(*) FROM tool_executions GROUP BY status")],
            "interactions": [list(row) for row in db.execute("SELECT state,count(*) FROM tool_chats GROUP BY state")],
            "running_tools": db.execute("SELECT count(*) FROM tool_executions WHERE status='running'").fetchone()[0],
            "memory_model_calls": db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0],
            "scoring_model_calls": db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0],
            "cancelled_chats_with_retained_data": db.execute("SELECT count(*) FROM tool_chats WHERE state='cancelled' AND data!='{}'").fetchone()[0],
            "deleted_tools_with_retained_result": db.execute("SELECT count(*) FROM tool_executions WHERE status='deleted' AND result!='{}'").fetchone()[0],
        }
    assert ledger["quick_check"] == "ok"
    assert ledger["network_requests"] == 6 and ledger["running_tools"] == 0
    assert ledger["memory_model_calls"] == ledger["scoring_model_calls"] == 0
    assert ledger["cancelled_chats_with_retained_data"] == ledger["deleted_tools_with_retained_result"] == 0
    costs["p05_public_request_ledger"] = ledger
    write_json("pause-api-usage.json", costs)

    ps = r"""
$processes = Get-CimInstance Win32_Process
$selected = $processes | Where-Object { $_.CommandLine -and ($_.CommandLine.Contains('p00-p07-20261103') -or $_.CommandLine -match 'playwright|lighthouse|mongod|pytest|acceptance_p05') }
$processRows = @($selected | ForEach-Object { [PSCustomObject]@{pid=$_.ProcessId;parent=$_.ParentProcessId;name=$_.Name;workspace=$_.CommandLine.Contains('p00-p07-20261103');test_candidate=$_.CommandLine -match 'playwright|lighthouse|mongod|pytest|acceptance_p05';shell=$_.Name -match 'powershell|pwsh'} })
$ports = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(3031,3091,3098,8031,5241,3461,8097,7475,7688) } | Select-Object LocalAddress,LocalPort,OwningProcess)
[PSCustomObject]@{processes=$processRows;listeners=$ports} | ConvertTo-Json -Depth 5 -Compress
"""
    services = json.loads(command(["powershell", "-NoProfile", "-Command", ps]))
    container_ids = []
    for project in ("lcr-acceptance-20261103", "lcr-p02-20261103"):
        container_ids.extend(command(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project]).splitlines())
    containers = []
    if container_ids:
        for container in json.loads(command(["docker", "inspect", *container_ids])):
            config = container["Config"]
            containers.append({
                "name": container["Name"], "state": container["State"]["Status"],
                "project": config["Labels"].get("com.docker.compose.project"),
                "service": config["Labels"].get("com.docker.compose.service"),
                "compose_workdir": config["Labels"].get("com.docker.compose.project.working_dir"),
                "mounts": [{"source": mount["Source"], "target": mount["Destination"], "rw": mount["RW"]} for mount in container["Mounts"]],
            })
    services["containers"] = containers
    services["checked_at"] = now
    services["health"] = {}
    for url in ("http://127.0.0.1:8031/health", "http://127.0.0.1:3031/health", "http://127.0.0.1:3091/login", "http://127.0.0.1:3031/life-api/api/v1/tool-chats"):
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        services["health"][url] = status
    assert list(services["health"].values()) == [200, 200, 200, 401]
    services["test_candidates_excluding_audit_shell"] = [
        row for row in services["processes"] if row["test_candidate"] and not row["shell"]]
    assert not services["test_candidates_excluding_audit_shell"]
    assert not any(row["LocalPort"] == 3098 for row in services["listeners"])
    write_json("pause-services.json", services)

    old = read_json("evidence/p05/chat-delivery-audit.json")
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in old["source_files"]}
    patch = read_json("evidence/p05/chat-upstream-patch-delivery-r2.json")
    assert hashlib.sha256((ROOT / patch["archive"]).read_bytes()).hexdigest() == patch["sha256"]
    assert patch["temporary_index_apply_check"] and patch["real_index_unchanged"]

    env = dotenv(ROOT / "infra/runtime/p00/acceptance.env")
    secret_values = {value.strip("'\"") for key, value in env.items()
                     if any(part in key.upper() for part in ("SECRET", "TOKEN", "API_KEY", "CREDS_KEY", "CREDS_IV"))
                     and len(value.strip("'\"")) >= 12}
    secret_files = [ROOT / "infra/runtime/p02/neo4j.env"]
    for secret_file in secret_files:
        if secret_file.exists():
            for key, value in dotenv(secret_file).items():
                if key == "NEO4J_AUTH" and "/" in value:
                    secret_values.add(value.split("/", 1)[1])
    scan_paths = set(ROOT / name for name in source_hashes)
    for base in ("evidence/p05", "docs/product/p00-p07/P05"):
        scan_paths.update(path for path in (ROOT / base).rglob("*") if path.is_file() and path.suffix.lower() in (".json", ".txt", ".md", ".log", ".py", ".cjs"))
    scan_paths.add(ROOT / "NEXT_ACTION.md")
    scan_paths.update((ROOT / "docs/product").glob("*2026-11-04.md"))
    scan_paths.update((ROOT / "docs/development-log").glob("2026-11-04_09-40_*.md"))
    scan_paths.update((ROOT / "patches").glob("*weather-chat*.patch"))
    for lighthouse in (ROOT / "products/librechat-custom/e2e/lighthouse/.lighthouse",
                       ROOT / "products/librechat-custom/.lighthouse"):
        if lighthouse.exists():
            scan_paths.update(path for path in lighthouse.rglob("*") if path.is_file())
    jwt_pattern = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
    findings = []
    for scan_path in sorted(scan_paths):
        text = scan_path.read_text(encoding="utf-8", errors="replace")
        known = sum(value in text for value in secret_values)
        jwts = len(jwt_pattern.findall(text))
        if known or jwts:
            findings.append({"path": str(scan_path.relative_to(ROOT)), "known_secret_matches": known, "jwt_matches": jwts})
    secret_scan = {"status": "PASS" if not findings else "FAIL", "files_scanned": len(scan_paths),
                   "scope": "18 weather source files, P05 evidence/docs, current progress report/pause log/NEXT_ACTION, weather patches, Lighthouse output; not a complete historical repository/privacy audit",
                   "findings": findings, "secret_values_printed": False}
    write_json("pause-sensitive-scan.json", secret_scan)
    assert not findings, "Sensitive material found; inspect sanitized scan report"

    audit = {
        "status": "PASS", "phase_status": "PARTIAL", "checked_at": now,
        "identity": identity, "nested_head": git["nested_head"], "source_files": source_hashes,
        "source_count": len(source_hashes), "ledger": ledger, "health": services["health"],
        "patch_sha256": patch["sha256"], "patch_evidence": "chat-upstream-patch-delivery-r2.json",
        "sensitive_scan": secret_scan,
        "weather_increment_added_public_requests": 2, "closeout_audit_added_external_requests": 0,
        "weather_increment_added_model_and_image_requests": 0,
        "tests": {"core": 167, "frontend_weather_reminder": 9, "native_bridge_final": 7, "gateway_and_log_redaction": 5},
        "performance_status": "PARTIAL; NO_NAVSTART; no complete three-run gate",
        "inherited_reminder_lint": "FAIL reproduced in before snapshot; outside changed lines",
        "safe_pause": "No active weather/test process; weather state cancelled; results cleared; ledger preserved; existing isolated services retained.",
        "pause_boundary": "Only P05 weather closeout and progress audit. Await explicit user authorization; no route/search/voice/followup/P06/P07 development.",
    }
    write_json("chat-delivery-audit-r2.json", audit)
    print(json.dumps({"status": "PASS", "checked_at": now, "root_dirty_count": git["root_dirty_count"],
                      "nested_dirty_count": git["nested_dirty_count"], "p05_network_requests": ledger["network_requests"],
                      "model_usage": dict(usage), "sensitive_scan": secret_scan["status"],
                      "active_test_processes": len(services["test_candidates_excluding_audit_shell"])}))


if __name__ == "__main__":
    main()
