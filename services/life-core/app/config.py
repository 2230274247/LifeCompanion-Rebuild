from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_path: Path
    internal_token: str
    jwt_secret: str
    jwt_refresh_secret: str
    memos_base_url: str
    memos_api_token: str
    timezone: str
    allowed_origins: tuple[str, ...]
    memory_llm_key: str = ""
    memory_llm_url: str = "https://api.deepseek.com/v1"
    memory_llm_model: str = "deepseek-chat"
    memory_llm_provider: str = "deepseek"
    memos_user_tokens: dict[str, str] = field(default_factory=dict)
    vikunja_base_url: str = "http://127.0.0.1:3456/api/v2"
    vikunja_users: dict[str, dict] = field(default_factory=dict)
    ntfy_base_url: str = "http://127.0.0.1:8087"
    ntfy_container: str = "lifecompanion-ntfy"
    ntfy_admin_user: str = ""
    ntfy_admin_password: str = ""
    reminder_webhook_url: str = "http://host.docker.internal:8010/api/v1/webhooks/vikunja"
    librechat_base_url: str = "http://127.0.0.1:3080"
    direct_moment_test_enabled: bool = False
    direct_moment_test_username: str = ""
    direct_moment_test_user_id: str = ""
    direct_moment_test_unlimited: bool = False
    moment_image_model: str = "cogview-4-250304"
    image_provider_api_key: str = ""
    image_provider_allow_generic_binary_mime: bool = False
    moment_min_score: float = .4
    memory_embedding_model: str = ""
    memory_embedding_cache: str = str(SERVICE_ROOT / "data" / "embedding-models")

    @property
    def memos_configured(self) -> bool:
        return bool(self.memos_api_token)

    @property
    def memory_llm_options(self) -> dict:
        return {"thinking": {"type": "disabled"}} if self.memory_llm_provider == "zhipu" else {}


def load_settings() -> Settings:
    provider = os.getenv("LIFE_LLM_PROVIDER", "deepseek").lower()
    if provider not in ("deepseek", "zhipu"):
        raise ValueError("UNSUPPORTED_LLM_PROVIDER")
    if provider == "zhipu":
        llm_key = os.getenv("ZHIPU_API_KEY", "")
        llm_url = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
        llm_model = os.getenv("ZHIPU_MODEL", "glm-4.7")
    else:
        llm_key = os.getenv("DEEPSEEK_API_KEY", "")
        llm_url = os.getenv("MEMORY_LLM_URL", "https://api.deepseek.com/v1")
        llm_model = os.getenv("MEMORY_LLM_MODEL", "deepseek-chat")
    tokens_file = os.getenv("LIFE_MEMOS_TOKENS_FILE")
    user_tokens = json.loads(Path(tokens_file).read_text(encoding="utf-8-sig")) if tokens_file else {}
    vikunja_users_file = os.getenv("LIFE_VIKUNJA_USERS_FILE")
    vikunja_users = (
        json.loads(Path(vikunja_users_file).read_text(encoding="utf-8-sig"))
        if vikunja_users_file
        else {}
    )
    database_path = Path(
        os.getenv("LIFE_DATABASE_PATH", SERVICE_ROOT / "data" / "life-core.sqlite3")
    )
    origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "LIFE_ALLOWED_ORIGINS",
            "http://localhost:3001,http://127.0.0.1:3001",
        ).split(",")
        if origin.strip()
    )
    return Settings(
        database_path=database_path,
        internal_token=os.getenv("LIFE_INTERNAL_TOKEN", ""),
        jwt_secret=os.getenv("JWT_SECRET", ""),
        jwt_refresh_secret=os.getenv("JWT_REFRESH_SECRET", ""),
        memos_base_url=os.getenv("MEMOS_BASE_URL", "http://127.0.0.1:5230").rstrip("/"),
        memos_api_token=os.getenv("MEMOS_API_TOKEN", ""),
        timezone=os.getenv("LIFE_TIMEZONE", "Asia/Hong_Kong"),
        allowed_origins=origins,
        memory_llm_key=llm_key,
        memory_llm_url=llm_url.rstrip("/"),
        memory_llm_model=llm_model,
        memory_llm_provider=provider,
        memos_user_tokens=user_tokens,
        vikunja_base_url=os.getenv(
            "LIFE_VIKUNJA_BASE_URL", "http://127.0.0.1:3456/api/v2"
        ).rstrip("/"),
        vikunja_users=vikunja_users,
        ntfy_base_url=os.getenv("LIFE_NTFY_BASE_URL", "http://127.0.0.1:8087").rstrip("/"),
        ntfy_container=os.getenv("LIFE_NTFY_CONTAINER", "lifecompanion-ntfy"),
        ntfy_admin_user=os.getenv("LIFE_NTFY_ADMIN_USER", ""),
        ntfy_admin_password=os.getenv("LIFE_NTFY_ADMIN_PASSWORD", ""),
        reminder_webhook_url=os.getenv(
            "LIFE_REMINDER_WEBHOOK_URL", "http://host.docker.internal:8010/api/v1/webhooks/vikunja"
        ),
        librechat_base_url=os.getenv("LIFE_LIBRECHAT_BASE_URL", "http://127.0.0.1:3080").rstrip("/"),
        moment_image_model=os.getenv("LIFE_MOMENT_IMAGE_MODEL", "cogview-4-250304"),
        direct_moment_test_enabled=(
            os.getenv("LIFE_DIRECT_MOMENT_TEST_ENABLED", "false").lower() == "true"
        ),
        direct_moment_test_username=os.getenv(
            "LIFE_DIRECT_MOMENT_TEST_USERNAME", ""
        ).strip(),
        direct_moment_test_user_id=os.getenv(
            "LIFE_DIRECT_MOMENT_TEST_USER_ID", ""
        ).strip(),
        direct_moment_test_unlimited=(
            os.getenv("LIFE_DIRECT_MOMENT_TEST_UNLIMITED", "false").lower() == "true"
        ),
        image_provider_api_key=(
            os.getenv("IMAGE_PROVIDER_API_KEY", "")
            or os.getenv("SILICONFLOW_API_KEY", "")
        ),
        image_provider_allow_generic_binary_mime=(
            os.getenv("IMAGE_PROVIDER_ALLOW_GENERIC_BINARY_MIME", "false").lower() == "true"
        ),
        moment_min_score=float(os.getenv("LIFE_MOMENT_MIN_SCORE", ".4")),
        memory_embedding_model=os.getenv("LIFE_MEMORY_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        memory_embedding_cache=os.getenv("LIFE_MEMORY_EMBEDDING_CACHE", str(SERVICE_ROOT / "data" / "embedding-models")),
    )

