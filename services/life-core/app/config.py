from __future__ import annotations

import os
from dataclasses import dataclass
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

    @property
    def memos_configured(self) -> bool:
        return bool(self.memos_api_token)


def load_settings() -> Settings:
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
    )

