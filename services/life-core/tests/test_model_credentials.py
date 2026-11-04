from __future__ import annotations

import json

import pytest

from app.config import load_settings
from app.model_credentials import (
    credential_diagnostics,
    load_model_keys,
    resolve_keys_file,
)


def write_keys(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# private test credentials\n"
        + "\n".join(f"{name}={value}" for name, value in values.items())
        + "\n",
        encoding="utf-8",
    )


def test_parent_file_is_authoritative_and_nonexistent_placeholders_are_ignored(tmp_path):
    repo = tmp_path / "LifeCompanion-Rebuild"
    repo.mkdir()
    keys = repo.parent / "model_api_keys.env"
    write_keys(keys, {
        "DEEPSEEK_API_KEY": "synthetic-deepseek",
        "IMAGE_PROVIDER_API_KEY": "synthetic-image",
        "DASHSCOPE_API_KEY": "",
        "UNKNOWN_PROVIDER_KEY": "must-not-load",
    })
    env = {"DEEPSEEK_API_KEY": "stale-environment-value"}
    result = load_model_keys(repo, environ=env)
    assert result["file_status"] == "LOADED"
    assert env["DEEPSEEK_API_KEY"] == "synthetic-deepseek"
    assert env["IMAGE_PROVIDER_API_KEY"] == "synthetic-image"
    assert "DASHSCOPE_API_KEY" not in env
    assert "UNKNOWN_PROVIDER_KEY" not in env


def test_diagnostics_expose_only_status_and_variable_names(tmp_path):
    repo = tmp_path / "LifeCompanion-Rebuild"
    repo.mkdir()
    env = {"SILICONFLOW_API_KEY": "must-not-appear-in-diagnostics"}
    diagnostics = credential_diagnostics(env)
    serialized = json.dumps(diagnostics, ensure_ascii=False)
    assert "must-not-appear-in-diagnostics" not in serialized
    assert diagnostics["providers"]["siliconflow"]["status"] == "SET"
    assert diagnostics["providers"]["deepseek"]["status"] == "MISSING"


def test_keys_file_override_must_be_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFECOMPANION_KEYS_FILE", "relative.env")
    with pytest.raises(ValueError, match="MUST_BE_ABSOLUTE"):
        resolve_keys_file(tmp_path)


def test_absolute_override_is_used(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    keys = tmp_path / "override.env"
    write_keys(keys, {"ZHIPU_API_KEY": "synthetic-zhipu"})
    env = {"LIFECOMPANION_KEYS_FILE": str(keys.resolve())}
    assert resolve_keys_file(repo, environ=env) == keys.resolve()
    result = load_model_keys(repo, environ=env)
    assert result["file_status"] == "LOADED"
    assert env["ZHIPU_API_KEY"] == "synthetic-zhipu"


def test_missing_parent_file_is_non_fatal(tmp_path):
    result = load_model_keys(tmp_path, environ={})
    assert result["file_status"] == "MISSING"
    assert result["loaded"] == []


def test_config_reads_image_provider_from_override_file(tmp_path, monkeypatch):
    keys = tmp_path / "model_api_keys.env"
    write_keys(keys, {
        "DEEPSEEK_API_KEY": "synthetic-deepseek",
        "IMAGE_PROVIDER_API_KEY": "synthetic-image",
    })
    monkeypatch.setenv("LIFECOMPANION_KEYS_FILE", str(keys.resolve()))
    monkeypatch.setenv("LIFE_MOMENT_IMAGE_PROVIDER", "kolors")
    settings = load_settings()
    assert settings.memory_llm_key == "synthetic-deepseek"
    assert settings.image_provider_api_key == "synthetic-image"
