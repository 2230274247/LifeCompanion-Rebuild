"""Fail closed before commands that may write to the audited Rebuild worktree."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUSINESS_MARKERS = (
    "services/life-core/app/main.py",
    "apps/product-portal/server.mjs",
    "infra/compose.baseline.yaml",
)


def git(directory: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(directory), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode:
        raise ValueError("NOT_A_REBUILD_REPOSITORY")
    return result.stdout.strip()


def verify(candidate: Path, target: Path | None = None) -> dict:
    lock_path = ROOT / "WORKSPACE_LOCK.json"
    lock = (
        json.loads(lock_path.read_text(encoding="utf-8"))
        if lock_path.is_file()
        else {}
    )
    canonical = Path(lock.get("canonical_root", ROOT)).resolve(strict=True)
    common = Path(git(canonical, "rev-parse", "--path-format=absolute",
                      "--git-common-dir")).resolve(strict=True)
    candidate = candidate.resolve(strict=True)
    top = Path(git(candidate, "rev-parse", "--show-toplevel")).resolve(strict=True)
    actual_common = Path(git(candidate, "rev-parse", "--path-format=absolute",
                            "--git-common-dir")).resolve(strict=True)
    audited = {
        Path(path).resolve(strict=True)
        for path in lock.get("audited_worktrees", [str(canonical)])
    }
    if actual_common != common or top not in audited:
        raise ValueError("UNAUDITED_OR_WRONG_REPOSITORY")
    if Path(git(canonical, "rev-parse", "--show-toplevel")).resolve() != canonical:
        raise ValueError("CANONICAL_NOT_TOP_LEVEL")
    if not all((top / marker).is_file() for marker in BUSINESS_MARKERS):
        raise ValueError("MISSING_BUSINESS_MARKERS")
    if target is not None:
        resolved = target.resolve()
        if not resolved.is_relative_to(top):
            raise ValueError("WRITE_TARGET_OUTSIDE_WORKTREE")
        for source in lock.get("read_only_source_roots", []):
            if resolved.is_relative_to(Path(source).resolve()):
                raise ValueError("READ_ONLY_SOURCE")
    return {
        "status": "PASS",
        "project_id": lock.get("project_id", "LifeCompanion-Rebuild"),
        "worktree": str(top),
        "git_common_dir": str(actual_common),
        "branch": git(top, "branch", "--show-current"),
        "head": git(top, "rev-parse", "HEAD"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=Path.cwd())
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.candidate, args.target)))
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        raise SystemExit(2)
