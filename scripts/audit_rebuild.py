"""Read-only identity/data audit. Never records credentials or message contents."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from verify_rebuild_workspace import ROOT, CANONICAL_ROOT, verify

verify(ROOT)
OUTPUT = ROOT / "evidence/p00"
OUTPUT.mkdir(parents=True, exist_ok=True)


def command(args, timeout=15):
    try:
        result = subprocess.run(args, capture_output=True, encoding="utf-8",
                                errors="replace", timeout=timeout)
        return {"exit_code": result.returncode, "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "error": "TIMEOUT", "timeout_seconds": timeout}


def git(path, *args):
    return command(["git", "--no-optional-locks", "-c", "core.quotepath=false",
                    "-C", str(path), *args])


def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def repository(path):
    result = {"path": str(path.resolve()), "exists": path.exists()}
    if not path.exists():
        return result
    for key, args in {
        "top": ("rev-parse", "--show-toplevel"),
        "common": ("rev-parse", "--path-format=absolute", "--git-common-dir"),
        "head": ("rev-parse", "HEAD"), "branch": ("branch", "--show-current"),
        "status": ("status", "--porcelain=v1"),
        "worktrees": ("worktree", "list", "--porcelain"),
    }.items():
        result[key] = git(path, *args)
    # Only credential-free HTTPS/SSH remote host and repository paths are recorded.
    remote = git(path, "remote", "get-url", "origin")
    value = remote.get("stdout", "")
    result["origin"] = value if "@" not in value and "?" not in value else "REDACTED_REMOTE"
    result["status_entry_count"] = len(result["status"].get("stdout", "").splitlines())
    return result


def source_fingerprints(path):
    paths = git(path, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if paths["exit_code"] != 0:
        # Research root is a collection, not a repository. Hash only root documents.
        files = [p for p in path.iterdir() if p.is_file() and p.suffix in (".md", ".txt", ".json")]
    else:
        files = [path / p for p in paths["stdout"].split("\0") if p and
                 not p.startswith((".work/", ".agents/", "docs/demos/", "docs/testing/"))]
    return {str(p.relative_to(path)): sha(p) for p in sorted(files)
            if p.is_file() and p.suffix in (".py", ".ts", ".vue", ".md", ".toml")
            and p.stat().st_size < 2_000_000}


def database_metadata(path):
    if not path.exists():
        return {"path": str(path), "exists": False}
    result = {"path": str(path), "exists": True, "sha256": sha(path)}
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        result["tables"] = {}
        for (table,) in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            result["tables"][table] = {
                "rows": connection.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0],
                "columns": [row[1] for row in connection.execute(f"PRAGMA table_info({quoted})")],
            }
    finally:
        connection.close()
    return result


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "before"
    if label not in ("before", "after"):
        raise SystemExit("Use before or after")
    parents = CANONICAL_ROOT.parent
    sources = [parents / "Silver-economy", parents / "Silver-economy-research",
               parents / "Silver-economy/.work/intelligence-20261103"]
    audit = {
        "at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
        "workspace": verify(ROOT), "canonical": repository(CANONICAL_ROOT),
        "sources": [repository(p) for p in sources],
        "source_sha256": {str(p): source_fingerprints(p) for p in sources if p.exists()},
        "upstreams": {name: repository(CANONICAL_ROOT / "products" / name)
                      for name in ("librechat-custom", "memos-custom", "vikunja-upstream",
                                   "ntfy-upstream")},
        "existing_databases": [
            database_metadata(CANONICAL_ROOT / "services/life-core/data/life-core.sqlite3")
        ],
        "docker": command(["docker", "ps", "-a", "--format",
                           "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"], timeout=8),
    }
    output = OUTPUT / f"identity-{label}.json"
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "evidence": str(output), "source_files_hashed": {
            key: len(value) for key, value in audit["source_sha256"].items()},
        "docker_exit": audit["docker"]["exit_code"],
    }))


if __name__ == "__main__":
    main()
