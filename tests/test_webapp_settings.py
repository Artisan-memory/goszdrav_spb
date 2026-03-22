from goszdrav_bot.config import Settings


def test_has_telegram_webapp_accepts_https() -> None:
    settings = Settings.model_validate(
        {
            "BOT_TOKEN": "test-token",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "WEBAPP_BASE_URL": "https://example.com",
            "FIELD_ENCRYPTION_SECRET": "secret-secret-secret",
            "FIELD_ENCRYPTION_SALT": "salt-value",
        }
    )

    assert settings.has_telegram_webapp is True


def test_has_telegram_webapp_rejects_http_localhost() -> None:
    settings = Settings.model_validate(
        {
            "BOT_TOKEN": "test-token",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "WEBAPP_BASE_URL": "http://localhost:8085",
            "FIELD_ENCRYPTION_SECRET": "secret-secret-secret",
            "FIELD_ENCRYPTION_SALT": "salt-value",
        }
    )

    assert settings.has_telegram_webapp is False
