"""Safe local probe; reports addresses, identities and counts, never secrets/content."""
import hashlib
import json
import sqlite3
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
result = {"root": str(root), "services": {}}
for name, port in (("gateway", 3001), ("chat", 3080), ("core", 8010), ("core-v023", 8023)):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
            result["services"][name] = {"port": port, "status": response.status}
    except Exception:
        result["services"][name] = {"port": port, "status": "unavailable"}
path = root / "services/life-core/data/life-core.sqlite3"
result["database"] = {"exists": path.exists(), "id": hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]}
if path.exists():
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result["database"]["tables"] = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            for t in ("users", "memory_items", "memory_jobs") if t in tables}
print(json.dumps(result, ensure_ascii=True, indent=2))
