from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from goszdrav_bot.bot.commands import apply_bot_commands
from goszdrav_bot.bot.handlers import common_router, profile_router
from goszdrav_bot.config import get_settings
from goszdrav_bot.core.logging import setup_logging
from goszdrav_bot.db.session import Database
from goszdrav_bot.services.crypto import FieldCipher
from goszdrav_bot.scraper.service import AsyncGorzdravScraper

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    db = Database(settings.database_url)
    scraper = AsyncGorzdravScraper(settings)
    cipher = FieldCipher(
        secret=settings.field_encryption_secret.get_secret_value(),
        salt=settings.field_encryption_salt.get_secret_value(),
    )

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(common_router)
    dispatcher.include_router(profile_router)

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await apply_bot_commands(bot, settings)
        logger.info("Bot polling started")
        await dispatcher.start_polling(
            bot,
            settings=settings,
            db=db,
            cipher=cipher,
            scraper=scraper,
        )
    finally:
        logger.info("Bot shutting down")
        await bot.session.close()
        await scraper.close()
        await db.dispose()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
