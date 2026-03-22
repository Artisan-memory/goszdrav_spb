from goszdrav_bot.config import Settings


def test_parse_single_bot_admin_id_from_int() -> None:
    settings = Settings.model_validate(
        {
            "BOT_TOKEN": "test-token",
            "BOT_ADMIN_IDS": 123456789,
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "FIELD_ENCRYPTION_SECRET": "secret-secret-secret",
            "FIELD_ENCRYPTION_SALT": "salt-value",
        }
    )

    assert settings.bot_admin_ids == [123456789]


def test_parse_multiple_bot_admin_ids_from_csv() -> None:
    settings = Settings.model_validate(
        {
            "BOT_TOKEN": "test-token",
            "BOT_ADMIN_IDS": "1, 2,3",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "FIELD_ENCRYPTION_SECRET": "secret-secret-secret",
            "FIELD_ENCRYPTION_SALT": "salt-value",
        }
    )

    assert settings.bot_admin_ids == [1, 2, 3]


def test_gorzdrav_api_base_url_defaults_to_official_api() -> None:
    settings = Settings.model_validate(
        {
            "BOT_TOKEN": "test-token",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "FIELD_ENCRYPTION_SECRET": "secret-secret-secret",
            "FIELD_ENCRYPTION_SALT": "salt-value",
        }
    )

    assert settings.gorzdrav_api_base_url == "https://gorzdrav.spb.ru/_api/api"
