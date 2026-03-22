from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="goszdrav-bot", alias="APP_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    bot_token: SecretStr = Field(alias="BOT_TOKEN")
    bot_admin_ids: list[int] = Field(default_factory=list, alias="BOT_ADMIN_IDS")

    database_url: str = Field(alias="DATABASE_URL")

    gorzdrav_base_url: str = Field(
        default="https://gorzdrav.spb.ru/service-free-schedule",
        alias="GORZDRAV_BASE_URL",
    )
    gorzdrav_api_base_url: str = Field(
        default="https://gorzdrav.spb.ru/_api/api",
        alias="GORZDRAV_API_BASE_URL",
    )
    gorzdrav_proxy_url: str | None = Field(default=None, alias="GORZDRAV_PROXY_URL")
    gorzdrav_api_proxy_url: str | None = Field(default=None, alias="GORZDRAV_API_PROXY_URL")
    gorzdrav_selenium_proxy_url: str | None = Field(
        default=None,
        alias="GORZDRAV_SELENIUM_PROXY_URL",
    )
    scraper_max_workers: int = Field(default=2, alias="SCRAPER_MAX_WORKERS")
    selenium_headless: bool = Field(default=True, alias="SELENIUM_HEADLESS")
    selenium_timeout_seconds: int = Field(default=20, alias="SELENIUM_TIMEOUT_SECONDS")
    selenium_chrome_binary: str | None = Field(default=None, alias="SELENIUM_CHROME_BINARY")
    monitor_interval_seconds: int = Field(default=120, alias="MONITOR_INTERVAL_SECONDS")
    notify_cooldown_seconds: int = Field(default=900, alias="NOTIFY_COOLDOWN_SECONDS")

    webapp_base_url: str | None = Field(default=None, alias="WEBAPP_BASE_URL")
    webapp_session_ttl_seconds: int = Field(default=86_400, alias="WEBAPP_SESSION_TTL_SECONDS")
    webapp_dev_mode: bool = Field(default=False, alias="WEBAPP_DEV_MODE")
    webapp_dev_telegram_id: int | None = Field(default=None, alias="WEBAPP_DEV_TELEGRAM_ID")

    field_encryption_secret: SecretStr = Field(alias="FIELD_ENCRYPTION_SECRET")
    field_encryption_salt: SecretStr = Field(alias="FIELD_ENCRYPTION_SALT")

    @field_validator("bot_admin_ids", mode="before")
    @classmethod
    def parse_bot_admin_ids(cls, value: Any) -> list[int]:
        if value in (None, "", []):
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            return [int(item) for item in value]
        if isinstance(value, tuple | set):
            return [int(item) for item in value]
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        raise TypeError("BOT_ADMIN_IDS must be int, comma-separated string, or list[int].")

    @field_validator(
        "gorzdrav_proxy_url",
        "gorzdrav_api_proxy_url",
        "gorzdrav_selenium_proxy_url",
        mode="before",
    )
    @classmethod
    def validate_proxy_url(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise TypeError("Proxy URL must be a string.")

        raw_value = value.strip()
        parsed = urlparse(raw_value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Proxy URL must include scheme and host, for example http://host:port.")
        if parsed.scheme.lower() == "mtproto":
            raise ValueError("MTProto proxy is not supported for Goszdrav HTTP/Selenium traffic.")
        return raw_value

    @property
    def has_webapp(self) -> bool:
        return bool(self.webapp_base_url)

    @property
    def has_telegram_webapp(self) -> bool:
        if not self.webapp_base_url:
            return False
        parsed = urlparse(self.webapp_base_url)
        return parsed.scheme == "https" and bool(parsed.netloc)

    @property
    def webapp_profile_url(self) -> str | None:
        if not self.webapp_base_url:
            return None
        return f"{self.webapp_base_url.rstrip('/')}/webapp/profile"

    @property
    def effective_gorzdrav_api_proxy_url(self) -> str | None:
        return self.gorzdrav_api_proxy_url or self.gorzdrav_proxy_url

    @property
    def effective_gorzdrav_selenium_proxy_url(self) -> str | None:
        return self.gorzdrav_selenium_proxy_url or self.gorzdrav_proxy_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
