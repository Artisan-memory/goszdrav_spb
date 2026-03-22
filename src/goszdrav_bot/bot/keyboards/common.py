from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from goszdrav_bot.config import Settings
from goszdrav_bot.core.districts import DISTRICTS


def main_menu_keyboard(settings: Settings) -> ReplyKeyboardMarkup:
    keyboard = []
    if settings.has_telegram_webapp and settings.webapp_profile_url:
        keyboard.append(
            [
                KeyboardButton(
                    text="Открыть Mini App",
                    web_app=WebAppInfo(url=settings.webapp_profile_url),
                )
            ]
        )
    keyboard.append([KeyboardButton(text="Профиль")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def profile_actions_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    buttons = []
    if settings.has_telegram_webapp and settings.webapp_profile_url:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="Открыть Mini App",
                    web_app=WebAppInfo(url=settings.webapp_profile_url),
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="Заполнить в чате", callback_data="profile:start_setup")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def district_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, title in DISTRICTS:
        builder.button(text=title, callback_data=f"district:{code}")
    builder.adjust(3)
    return builder.as_markup()


def organization_keyboard(organizations: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for external_id, label in organizations:
        compact = label if len(label) <= 56 else f"{label[:53].rstrip()}..."
        builder.button(text=compact, callback_data=f"profile:org:{external_id}")
    builder.adjust(1)
    return builder.as_markup()
