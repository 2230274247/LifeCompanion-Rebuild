from app.config import load_settings


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
