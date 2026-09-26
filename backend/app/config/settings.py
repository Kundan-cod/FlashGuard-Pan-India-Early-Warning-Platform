"""
Track B settings (master prompt sections 36, 55) — pydantic-settings.

Secrets and connection strings come from the environment / .env ONLY; nothing
is hard-coded here. This mirrors the Track A convention (PORTABLE_DB_PATH env)
so the two tracks share the same "config from environment" discipline.
"""
from __future__ import annotations

from functools import lru_cache

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field
except ImportError:  # pragma: no cover - Track B dep not installed in sandbox
    BaseSettings = object  # type: ignore
    SettingsConfigDict = dict  # type: ignore
    def Field(default=None, **_):  # type: ignore
        return default


class Settings(BaseSettings):  # type: ignore[misc]
    app_mode: str = Field("replay", alias="APP_MODE")           # live|replay|simulation
    database_url: str = Field(
        "postgresql+psycopg2://flashguard:changeme_local_only@localhost:5432/flashguard",
        alias="DATABASE_URL")
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")

    # External source credentials (verified sources only; blank until verified).
    nasa_earthdata_token: str | None = Field(None, alias="NASA_EARTHDATA_TOKEN")
    imd_api_key: str | None = Field(None, alias="IMD_API_KEY")
    mosdac_api_key: str | None = Field(None, alias="MOSDAC_API_KEY")
    cwc_api_key: str | None = Field(None, alias="CWC_API_KEY")
    gsi_api_key: str | None = Field(None, alias="GSI_API_KEY")
    bhuvan_api_key: str | None = Field(None, alias="BHUVAN_API_KEY")
    ndem_api_key: str | None = Field(None, alias="NDEM_API_KEY")
    iot_device_shared_secret: str | None = Field(None, alias="IOT_DEVICE_SHARED_SECRET")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore",
                                      populate_by_name=True)


@lru_cache
def get_settings() -> "Settings":
    return Settings()
