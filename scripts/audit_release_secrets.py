"""Check known cloud-key values against release files and Git history."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


KEY_NAMES = (
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "ZHIPU_API_KEY",
    "MOONSHOT_API_KEY",
    "OPENAI_API_KEY",
    "IMAGE_PROVIDER_API_KEY",
    "SILICONFLOW_API_KEY",
)


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def load_keys(path: Path) -> dict[str, str]:
    keys: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("'\"")
        if name in KEY_NAMES and len(value) >= 8:
            keys[name] = value
    return keys


def release_files(repo: Path) -> list[Path]:
    raw = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return [
        repo / item.decode("utf-8", "surrogateescape")
        for item in raw.split(b"\0")
        if item
    ]


def history_blobs(repo: Path) -> list[tuple[str, bytes]]:
    objects = git(repo, "rev-list", "--objects", "--all")
    hashes = []
    for line in objects.decode("utf-8", "replace").splitlines():
        fields = line.split(maxsplit=1)
        if fields and len(fields[0]) == 40:
            hashes.append(fields[0].encode())
    if not hashes:
        return []
    checked = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input=b"\n".join(hashes) + b"\n",
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", "replace").splitlines()
    blob_hashes = [
        line.split()[0]
        for line in checked
        if len(line.split()) == 2 and line.split()[1] == "blob"
    ]
    if not blob_hashes:
        return []
    batch = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=("\n".join(blob_hashes) + "\n").encode(),
        capture_output=True,
        check=True,
    ).stdout
    blobs: list[tuple[str, bytes]] = []
    position = 0
    for _ in blob_hashes:
        newline = batch.index(b"\n", position)
        header = batch[position:newline].decode("utf-8", "replace").split()
        position = newline + 1
        if len(header) < 3 or header[1] != "blob":
            continue
        size = int(header[2])
        content = batch[position:position + size]
        position += size + 1
        blobs.append((header[0], content))
    return blobs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--keys-file", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    lock_path = repo / "WORKSPACE_LOCK.json"
    project_root = repo
    if lock_path.is_file():
        project_root = Path(
            json.loads(lock_path.read_text(encoding="utf-8"))["canonical_root"]
        ).resolve()
    keys_file = (
        args.keys_file
        or Path(
            os.environ.get(
                "LIFECOMPANION_KEYS_FILE",
                project_root.parent / "model_api_keys.env",
            )
        )
    ).resolve()
    if not keys_file.is_file():
        print(json.dumps({"status": "BLOCKED", "reason": "KEYS_FILE_MISSING"}))
        return 2

    keys = load_keys(keys_file)
    findings = []
    files = release_files(repo)
    for path in files:
        if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        relative = path.relative_to(repo).as_posix()
        for name, value in keys.items():
            if value.encode() in content:
                findings.append({"scope": "worktree", "name": name, "path": relative})

    blobs = history_blobs(repo)
    for object_id, content in blobs:
        for name, value in keys.items():
            if value.encode() in content:
                findings.append({"scope": "history", "name": name, "object": object_id})

    report = {
        "status": "FAIL" if findings else "PASS",
        "keys_file": str(keys_file),
        "configured_key_names": sorted(keys),
        "checked_worktree_files": len(files),
        "checked_history_blobs": len(blobs),
        "findings": findings,
    }
    print(json.dumps(report, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
