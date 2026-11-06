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
    memory_llm_model: str = "deepseek-flash"
    memory_llm_provider: str = "deepseek"
    memory_llm_max_tokens: int = 2048
    memory_llm_request_budget: int = 0
    memos_user_tokens: dict[str, str] = field(default_factory=dict)
    vikunja_base_url: str = "http://127.0.0.1:3456/api/v2"
    vikunja_users: dict[str, dict] = field(default_factory=dict)
    ntfy_base_url: str = "http://127.0.0.1:8087"
    ntfy_container: str = "lifecompanion-ntfy"
    reminder_webhook_url: str = "http://host.docker.internal:8010/api/v1/webhooks/vikunja"
    librechat_base_url: str = "http://127.0.0.1:3080"
    moment_image_model: str = "cogview-4-250304"
    moment_min_score: float = .4
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    reminder_scheduler_db: str = ""
    reminder_scheduler_external: bool = False
    embedding_provider: str = ""
    embedding_api_key: str = ""

    @property
    def memos_configured(self) -> bool:
        return bool(self.memos_api_token)

    @property
    def memory_llm_options(self) -> dict:
        return {"thinking": {"type": "disabled"}}


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
        llm_url = os.getenv("MEMORY_LLM_URL") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        llm_model = os.getenv("MEMORY_LLM_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    max_tokens = int(os.getenv("MEMORY_LLM_MAX_TOKENS", "2048"))
    request_budget = int(os.getenv("MEMORY_LLM_REQUEST_BUDGET", "0"))
    if max_tokens <= 0 or request_budget < 0:
        raise ValueError("INVALID_MEMORY_LLM_LIMIT")
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
        memory_llm_max_tokens=max_tokens,
        memory_llm_request_budget=request_budget,
        memos_user_tokens=user_tokens,
        vikunja_base_url=os.getenv(
            "LIFE_VIKUNJA_BASE_URL", "http://127.0.0.1:3456/api/v2"
        ).rstrip("/"),
        vikunja_users=vikunja_users,
        ntfy_base_url=os.getenv("LIFE_NTFY_BASE_URL", "http://127.0.0.1:8087").rstrip("/"),
        ntfy_container=os.getenv("LIFE_NTFY_CONTAINER", "lifecompanion-ntfy"),
        reminder_webhook_url=os.getenv(
            "LIFE_REMINDER_WEBHOOK_URL", "http://host.docker.internal:8010/api/v1/webhooks/vikunja"
        ),
        librechat_base_url=os.getenv("LIFE_LIBRECHAT_BASE_URL", "http://127.0.0.1:3080").rstrip("/"),
        moment_image_model=os.getenv("LIFE_MOMENT_IMAGE_MODEL", "cogview-4-250304"),
        moment_min_score=float(os.getenv("LIFE_MOMENT_MIN_SCORE", ".4")),
        neo4j_uri=os.getenv("LIFE_NEO4J_URI", ""),
        neo4j_user=os.getenv("LIFE_NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("LIFE_NEO4J_PASSWORD", ""),
        reminder_scheduler_db=os.getenv("LIFE_REMINDER_SCHEDULER_DB", ""),
        reminder_scheduler_external=os.getenv("LIFE_REMINDER_SCHEDULER_EXTERNAL", "false").lower() == "true",
        embedding_provider=os.getenv("LIFE_EMBEDDING_PROVIDER", ""),
        embedding_api_key=os.getenv("LIFE_EMBEDDING_API_KEY", ""),
    )

