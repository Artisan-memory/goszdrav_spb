from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from goszdrav_bot.core.districts import DISTRICT_BY_CODE


class TelegramIdentity(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=3, max_length=255)
    email: EmailStr | None = None
    birth_date: date | None = None
    district_code: str | None = Field(default=None, max_length=64)
    organization_external_id: str | None = Field(default=None, max_length=128)
    organization_label: str | None = Field(default=None, max_length=255)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator(
        "organization_external_id",
        "organization_label",
    )
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("district_code")
    @classmethod
    def validate_district_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in DISTRICT_BY_CODE:
            raise ValueError("Неизвестный код района.")
        return normalized

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date | None) -> date | None:
        if value is None:
            return value
        if value > date.today():
            raise ValueError("Дата рождения не может быть в будущем.")
        return value


class ProfileView(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None

    full_name: str | None = None
    email: EmailStr | None = None
    birth_date: date | None = None
    district_code: str | None = None
    district_title: str | None = None
    organization_external_id: str | None = None
    organization_label: str | None = None

    is_complete: bool = False
