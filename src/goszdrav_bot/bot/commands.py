from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

from goszdrav_bot.config import Settings


def build_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Открыть главное меню"),
        BotCommand(command="profile", description="Открыть профиль"),
    ]


async def apply_bot_commands(bot: Bot, settings: Settings) -> None:
    await bot.set_my_commands(build_bot_commands())
    if settings.has_telegram_webapp and settings.webapp_profile_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть Mini App",
                web_app=WebAppInfo(url=settings.webapp_profile_url),
            )
        )
        return
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
