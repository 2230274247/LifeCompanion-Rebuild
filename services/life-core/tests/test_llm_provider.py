from app.config import load_settings
import pytest


@pytest.fixture(autouse=True)
def isolate_parent_credentials(monkeypatch):
    monkeypatch.setattr(
        "app.config.load_model_keys",
        lambda *args, **kwargs: {
            "file_status": "TEST_ISOLATED",
            "loaded": [],
        },
    )


def test_deepseek_uses_its_own_credentials_and_bounded_output(monkeypatch):
    monkeypatch.setenv("LIFE_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example/v1/")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")
    monkeypatch.setenv("ZHIPU_API_KEY", "must-not-be-used")
    monkeypatch.delenv("MEMORY_LLM_URL", raising=False)
    monkeypatch.delenv("MEMORY_LLM_MODEL", raising=False)
    monkeypatch.setenv("MEMORY_LLM_MAX_TOKENS", "1024")
    monkeypatch.setenv("MEMORY_LLM_REQUEST_BUDGET", "12")
    settings = load_settings()
    assert settings.memory_llm_key == "synthetic-deepseek-key"
    assert settings.memory_llm_model == "deepseek-test"
    assert settings.memory_llm_url == "https://deepseek.example/v1"
    assert settings.memory_llm_options == {"thinking": {"type": "disabled"}}
    assert settings.memory_llm_max_tokens == 1024
    assert settings.memory_llm_request_budget == 12


def test_deepseek_memory_overrides_preserve_existing_api_configuration(monkeypatch):
    monkeypatch.setenv("LIFE_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://unused.example/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "unused-model")
    monkeypatch.setenv("MEMORY_LLM_URL", "https://existing.example/v1/")
    monkeypatch.setenv("MEMORY_LLM_MODEL", "existing-model")
    settings = load_settings()
    assert settings.memory_llm_url == "https://existing.example/v1"
    assert settings.memory_llm_model == "existing-model"


def test_missing_deepseek_key_never_falls_back_to_zhipu(monkeypatch):
    monkeypatch.setenv("LIFE_LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("ZHIPU_API_KEY", "must-not-be-used")
    assert load_settings().memory_llm_key == ""


@pytest.mark.parametrize(("name", "value"), [
    ("MEMORY_LLM_MAX_TOKENS", "0"), ("MEMORY_LLM_REQUEST_BUDGET", "-1"),
])
def test_invalid_generation_limits_fail_closed(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="INVALID_MEMORY_LLM_LIMIT"):
        load_settings()


def test_zhipu_provider_uses_its_own_credentials_and_options(monkeypatch):
    monkeypatch.setenv("LIFE_LLM_PROVIDER", "zhipu")
    monkeypatch.setenv("ZHIPU_API_KEY", "synthetic-zhipu-key")
    monkeypatch.setenv("ZHIPU_MODEL", "glm-test")
    monkeypatch.setenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-be-used")
    settings = load_settings()
    assert settings.memory_llm_key == "synthetic-zhipu-key"
    assert settings.memory_llm_model == "glm-test"
    assert settings.memory_llm_url == "https://open.bigmodel.cn/api/paas/v4"
    assert settings.memory_llm_options == {"thinking": {"type": "disabled"}}


def test_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.setenv("LIFE_LLM_PROVIDER", "unknown")
    try:
        load_settings()
    except ValueError as exc:
        assert str(exc) == "UNSUPPORTED_LLM_PROVIDER"
    else:
        raise AssertionError("Unknown provider must fail closed")


def test_missing_zhipu_key_never_falls_back_to_deepseek(monkeypatch):
    monkeypatch.setenv("LIFE_LLM_PROVIDER", "zhipu")
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-be-used")
    assert load_settings().memory_llm_key == ""
