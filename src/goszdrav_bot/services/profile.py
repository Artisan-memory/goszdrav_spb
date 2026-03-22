from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goszdrav_bot.core.districts import DISTRICT_BY_CODE
from goszdrav_bot.db.models import TelegramUser, UserProfile
from goszdrav_bot.schemas.profile import ProfilePatch, ProfileView, TelegramIdentity
from goszdrav_bot.services.crypto import FieldCipher


class ProfileService:
    def __init__(self, session: AsyncSession, cipher: FieldCipher) -> None:
        self.session = session
        self.cipher = cipher

    async def ensure_user(self, identity: TelegramIdentity) -> TelegramUser:
        user = await self._get_user(identity.telegram_id)
        if user is None:
            user = TelegramUser(
                telegram_id=identity.telegram_id,
                username=identity.username,
                first_name=identity.first_name,
                last_name=identity.last_name,
                language_code=identity.language_code,
                profile=UserProfile(),
            )
            self.session.add(user)
        else:
            user.username = identity.username
            user.first_name = identity.first_name
            user.last_name = identity.last_name
            user.language_code = identity.language_code
            if user.profile is None:
                user.profile = UserProfile()

        await self.session.flush()
        return user

    async def get_profile(self, telegram_id: int) -> ProfileView | None:
        user = await self._get_user(telegram_id)
        if user is None:
            return None
        return self._to_view(user)

    def profile_from_user(self, user: TelegramUser) -> ProfileView:
        return self._to_view(user)

    async def upsert_profile(
        self,
        telegram_id: int,
        payload: ProfilePatch,
        identity: TelegramIdentity | None = None,
    ) -> ProfileView:
        if identity:
            user = await self.ensure_user(identity)
        else:
            user = await self._get_or_create_user(telegram_id)

        profile = user.profile or UserProfile(user=user)
        user.profile = profile

        data = payload.model_dump(exclude_unset=True)
        self._reset_dependent_fields(profile, data)
        if "full_name" in data:
            profile.full_name_encrypted = self.cipher.encrypt(data["full_name"])
        if "email" in data:
            profile.email_encrypted = self.cipher.encrypt(str(data["email"]) if data["email"] else None)
        if "birth_date" in data:
            birth_date = data["birth_date"]
            profile.birth_date_encrypted = self.cipher.encrypt(
                birth_date.isoformat() if birth_date else None
            )
        if "district_code" in data:
            profile.district_code = data["district_code"]
        if "organization_external_id" in data:
            profile.organization_external_id = data["organization_external_id"]
        if "organization_label" in data:
            profile.organization_label = data["organization_label"]

        profile.is_complete = all(
            [
                bool(profile.full_name_encrypted),
                bool(profile.email_encrypted),
                bool(profile.birth_date_encrypted),
                bool(profile.district_code),
                bool(profile.organization_label),
            ]
        )

        await self.session.flush()
        return self._to_view(user)

    @staticmethod
    def _reset_dependent_fields(profile: UserProfile, data: dict) -> None:
        district_changed = "district_code" in data and data["district_code"] != profile.district_code
        organization_changed = "organization_label" in data and data["organization_label"] != profile.organization_label

        if district_changed and "organization_external_id" not in data:
            profile.organization_external_id = None

        if district_changed and "organization_label" not in data:
            profile.organization_external_id = None
            profile.organization_label = None

        if organization_changed and "organization_external_id" not in data:
            profile.organization_external_id = None

        if "organization_label" in data and not data["organization_label"]:
            profile.organization_external_id = None

    async def _get_or_create_user(self, telegram_id: int) -> TelegramUser:
        user = await self._get_user(telegram_id)
        if user is not None:
            return user

        user = TelegramUser(telegram_id=telegram_id, profile=UserProfile())
        self.session.add(user)
        await self.session.flush()
        return user

    async def _get_user(self, telegram_id: int) -> TelegramUser | None:
        result = await self.session.execute(
            select(TelegramUser)
            .options(selectinload(TelegramUser.profile))
            .where(TelegramUser.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    def _to_view(self, user: TelegramUser) -> ProfileView:
        profile = user.profile or UserProfile()
        birth_date = self._parse_birth_date(self.cipher.decrypt(profile.birth_date_encrypted))
        email = self.cipher.decrypt(profile.email_encrypted)

        return ProfileView(
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=self.cipher.decrypt(profile.full_name_encrypted),
            email=email,
            birth_date=birth_date,
            district_code=profile.district_code,
            district_title=DISTRICT_BY_CODE.get(profile.district_code or ""),
            organization_external_id=profile.organization_external_id,
            organization_label=profile.organization_label,
            is_complete=profile.is_complete,
        )

    @staticmethod
    def _parse_birth_date(value: str | None) -> date | None:
        if not value:
            return None
        return date.fromisoformat(value)
