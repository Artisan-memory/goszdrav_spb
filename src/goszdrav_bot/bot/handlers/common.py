from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from goszdrav_bot.bot.commands import apply_bot_commands
from goszdrav_bot.bot.keyboards.common import main_menu_keyboard, profile_actions_keyboard
from goszdrav_bot.config import Settings
from goszdrav_bot.db.session import Database
from goszdrav_bot.schemas.profile import TelegramIdentity
from goszdrav_bot.services.crypto import FieldCipher
from goszdrav_bot.services.profile import ProfileService

router = Router(name=__name__)


def identity_from_message(message: Message) -> TelegramIdentity:
    user = message.from_user
    if user is None:
        raise ValueError("Message does not have Telegram user data.")
    return TelegramIdentity(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )


@router.message(CommandStart())
async def command_start(
    message: Message,
    bot: Bot,
    settings: Settings,
    db: Database,
    cipher: FieldCipher,
) -> None:
    await apply_bot_commands(bot, settings)
    async with db.session() as session:
        service = ProfileService(session, cipher)
        await service.ensure_user(identity_from_message(message))

    await message.answer(
        "Откройте Mini App для настройки профиля, наблюдений и автозаписи.\n"
        "Если Mini App недоступен, используйте заполнение через чат.",
        reply_markup=main_menu_keyboard(settings),
    )
    await message.answer(
        "Выберите способ настройки:",
        reply_markup=profile_actions_keyboard(settings),
    )
