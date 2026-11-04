from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from pathlib import Path

from .model_credentials import load_model_keys


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
    moment_image_model: str = "Kwai-Kolors/Kolors"
    moment_media_root: Path | None = None
    image_provider_api_key: str = ""
    image_provider_allow_generic_binary_mime: bool = False
    moment_min_score: float = .4
    moment_scoring_request_budget: int = 0
    moment_scoring_max_tokens: int = 1800
    moment_scoring_max_candidates: int = 8
    moment_prompt_request_budget: int = 0
    moment_prompt_max_tokens: int = 700
    moment_windows_v03: bool = False
    moment_settlement_scan_limit: int = 96
    moment_score_lease_seconds: int = 120
    moment_scheduler_external: bool = False
    moment_image_generation_enabled: bool = False
    moment_image_provider: str = ""
    moment_image_request_budget: int = 0
    direct_moment_test_enabled: bool = False
    direct_moment_test_username: str = ""
    direct_moment_test_unlimited: bool = False
    moment_workers_enabled: bool = True
    tool_request_budget: int = 0
    tool_weather_provider: str = ""
    tool_route_provider: str = ""
    tool_search_url: str = ""
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
    load_model_keys(SERVICE_ROOT.parent.parent)
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
    scoring_budget = int(os.getenv("LIFE_MOMENT_SCORING_REQUEST_BUDGET", "0"))
    scoring_tokens = int(os.getenv("LIFE_MOMENT_SCORING_MAX_TOKENS", "1800"))
    scoring_candidates = int(os.getenv("LIFE_MOMENT_SCORING_MAX_CANDIDATES", "8"))
    prompt_budget = int(os.getenv("LIFE_MOMENT_PROMPT_REQUEST_BUDGET", "0"))
    prompt_tokens = int(os.getenv("LIFE_MOMENT_PROMPT_MAX_TOKENS", "700"))
    image_budget = int(os.getenv("LIFE_MOMENT_IMAGE_REQUEST_BUDGET", "0"))
    settlement_scan_limit = int(os.getenv("LIFE_MOMENT_SETTLEMENT_SCAN_LIMIT", "96"))
    score_lease_seconds = int(os.getenv("LIFE_MOMENT_SCORE_LEASE_SECONDS", "120"))
    tool_budget = int(os.getenv("LIFE_TOOL_REQUEST_BUDGET", "0"))
    weather_provider = os.getenv("LIFE_TOOL_WEATHER_PROVIDER", "")
    route_provider = os.getenv("LIFE_TOOL_ROUTE_PROVIDER", "")
    if max_tokens <= 0 or request_budget < 0:
        raise ValueError("INVALID_MEMORY_LLM_LIMIT")
    if scoring_budget < 0 or not 256 <= scoring_tokens <= 4096 or not 1 <= scoring_candidates <= 16:
        raise ValueError("INVALID_MOMENT_SCORING_LIMIT")
    if prompt_budget < 0 or not 256 <= prompt_tokens <= 2048:
        raise ValueError("INVALID_MOMENT_PROMPT_LIMIT")
    if image_budget < 0:
        raise ValueError("INVALID_MOMENT_IMAGE_BUDGET")
    if not 1 <= settlement_scan_limit <= 1000 or not 30 <= score_lease_seconds <= 900:
        raise ValueError("INVALID_MOMENT_RECOVERY_LIMIT")
    if tool_budget < 0 or weather_provider not in ("","open_meteo") or route_provider not in ("","osrm_demo"):
        raise ValueError("INVALID_TOOL_CONFIGURATION")
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
    media_root = os.getenv("LIFE_MOMENT_MEDIA_ROOT", "").strip()
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
        moment_image_model=os.getenv(
            "LIFE_MOMENT_IMAGE_MODEL", "Kwai-Kolors/Kolors"
        ),
        moment_media_root=(
            Path(media_root) if media_root else database_path.parent / "moment-media"
        ),
        image_provider_api_key=(
            os.getenv("IMAGE_PROVIDER_API_KEY", "")
            or os.getenv("SILICONFLOW_API_KEY", "")
        ),
        image_provider_allow_generic_binary_mime=(
            os.getenv("IMAGE_PROVIDER_ALLOW_GENERIC_BINARY_MIME", "false").lower()
            == "true"
        ),
        moment_min_score=float(os.getenv("LIFE_MOMENT_MIN_SCORE", ".4")),
        moment_scoring_request_budget=scoring_budget,
        moment_scoring_max_tokens=scoring_tokens,
        moment_scoring_max_candidates=scoring_candidates,
        moment_prompt_request_budget=prompt_budget,
        moment_prompt_max_tokens=prompt_tokens,
        moment_windows_v03=os.getenv("LIFE_MOMENT_WINDOWS_V03", "false").lower() == "true",
        moment_settlement_scan_limit=settlement_scan_limit,
        moment_score_lease_seconds=score_lease_seconds,
        moment_scheduler_external=os.getenv("LIFE_MOMENT_SCHEDULER_EXTERNAL", "false").lower() == "true",
        moment_image_generation_enabled=os.getenv("LIFE_MOMENT_IMAGE_GENERATION_ENABLED", "false").lower() == "true",
        moment_image_provider=os.getenv("LIFE_MOMENT_IMAGE_PROVIDER", ""),
        moment_image_request_budget=image_budget,
        direct_moment_test_enabled=(
            os.getenv("LIFE_DIRECT_MOMENT_TEST_ENABLED", "false").lower() == "true"
        ),
        direct_moment_test_username=os.getenv(
            "LIFE_DIRECT_MOMENT_TEST_USERNAME", ""
        ).strip(),
        direct_moment_test_unlimited=(
            os.getenv("LIFE_DIRECT_MOMENT_TEST_UNLIMITED", "false").lower()
            == "true"
        ),
        moment_workers_enabled=os.getenv("LIFE_MOMENT_WORKERS_ENABLED", "true").lower() == "true",
        tool_request_budget=tool_budget,
        tool_weather_provider=weather_provider,
        tool_route_provider=route_provider,
        tool_search_url=os.getenv("LIFE_TOOL_SEARCH_URL",""),
        neo4j_uri=os.getenv("LIFE_NEO4J_URI", ""),
        neo4j_user=os.getenv("LIFE_NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("LIFE_NEO4J_PASSWORD", ""),
        reminder_scheduler_db=os.getenv("LIFE_REMINDER_SCHEDULER_DB", ""),
        reminder_scheduler_external=os.getenv("LIFE_REMINDER_SCHEDULER_EXTERNAL", "false").lower() == "true",
        embedding_provider=os.getenv("LIFE_EMBEDDING_PROVIDER", ""),
        embedding_api_key=os.getenv("LIFE_EMBEDDING_API_KEY", ""),
    )

