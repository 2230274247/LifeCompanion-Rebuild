"""Load cloud-model credentials from the project parent without exposing values."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import Lock


LOGGER = logging.getLogger("lifecompanion.credentials")
LOAD_LOCK = Lock()

PROVIDER_CREDENTIALS = {
    "deepseek": ("DEEPSEEK_API_KEY",),
    "dashscope": ("DASHSCOPE_API_KEY",),
    "zhipu": ("ZHIPU_API_KEY",),
    "moonshot": ("MOONSHOT_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "siliconflow": ("IMAGE_PROVIDER_API_KEY", "SILICONFLOW_API_KEY"),
}
KNOWN_KEYS = tuple(
    dict.fromkeys(
        name for names in PROVIDER_CREDENTIALS.values() for name in names
    )
)


def _repository_root() -> Path:
    # services/life-core/app -> life-core -> services -> repository
    return Path(__file__).resolve().parents[3]


def canonical_project_root(repository_root: Path | None = None) -> Path:
    root = (repository_root or _repository_root()).resolve()
    lock_file = root / "WORKSPACE_LOCK.json"
    if lock_file.is_file():
        try:
            lock = json.loads(lock_file.read_text(encoding="utf-8-sig"))
            canonical = Path(lock["canonical_root"]).resolve()
            if canonical.is_dir():
                return canonical
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return root


def resolve_keys_file(
    repository_root: Path | None = None,
    *,
    environ: dict | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    override = (env.get("LIFECOMPANION_KEYS_FILE") or "").strip()
    if override:
        path = Path(override)
        if not path.is_absolute():
            raise ValueError("LIFECOMPANION_KEYS_FILE_MUST_BE_ABSOLUTE")
        return path.resolve()
    return (canonical_project_root(repository_root).parent / "model_api_keys.env").resolve()


def parse_keys_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in KNOWN_KEYS:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value:
            values[name] = value
    return values


def load_model_keys(
    repository_root: Path | None = None,
    *,
    environ: dict | None = None,
) -> dict:
    """Load model keys into the process environment.

    The private parent file is authoritative for non-empty values. Process
    environment injection remains supported for container/secret-manager
    deployments when the file is absent.
    """
    env = os.environ if environ is None else environ
    with LOAD_LOCK:
        path = resolve_keys_file(repository_root, environ=env)
        if not path.is_file():
            LOGGER.warning("MODEL_API_KEYS_FILE MISSING path=%s", path)
            return {
                "path": str(path),
                "file_status": "MISSING",
                "loaded": [],
                "source": "environment",
            }
        try:
            values = parse_keys_file(path)
        except (OSError, UnicodeError) as exc:
            LOGGER.warning(
                "MODEL_API_KEYS_FILE UNREADABLE path=%s error=%s",
                path,
                type(exc).__name__,
            )
            return {
                "path": str(path),
                "file_status": "UNREADABLE",
                "loaded": [],
                "source": "environment",
            }
        for name, value in values.items():
            env[name] = value
        for provider, names in PROVIDER_CREDENTIALS.items():
            configured = any((env.get(name) or "").strip() for name in names)
            LOGGER.info(
                "MODEL_CREDENTIAL %s %s",
                provider,
                "SET" if configured else "MISSING",
            )
        return {
            "path": str(path),
            "file_status": "LOADED",
            "loaded": sorted(values),
            "source": "parent-file+environment",
        }


def credential_diagnostics(environ: dict | None = None) -> dict:
    env = os.environ if environ is None else environ
    providers = {}
    for provider, names in PROVIDER_CREDENTIALS.items():
        providers[provider] = {
            "status": (
                "SET"
                if any((env.get(name) or "").strip() for name in names)
                else "MISSING"
            ),
            "variables": list(names),
        }
    return {
        "keys_file": str(resolve_keys_file(environ=env)),
        "providers": providers,
        "available_providers": sorted(
            name
            for name, value in providers.items()
            if value["status"] == "SET"
        ),
    }


__all__ = [
    "KNOWN_KEYS",
    "PROVIDER_CREDENTIALS",
    "canonical_project_root",
    "credential_diagnostics",
    "load_model_keys",
    "parse_keys_file",
    "resolve_keys_file",
]
