from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from goszdrav_bot.config import get_settings
from goszdrav_bot.core.logging import setup_logging
from goszdrav_bot.db.session import Database
from goszdrav_bot.scraper.service import AsyncGorzdravScraper
from goszdrav_bot.services.crypto import FieldCipher
from goszdrav_bot.workers.monitor import SlotMonitor

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    db = Database(settings.database_url)
    cipher = FieldCipher(
        secret=settings.field_encryption_secret.get_secret_value(),
        salt=settings.field_encryption_salt.get_secret_value(),
    )
    scraper = AsyncGorzdravScraper(settings)
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    monitor = SlotMonitor(db=db, scraper=scraper, cipher=cipher, settings=settings, bot=bot)

    try:
        while True:
            try:
                results = await monitor.scan_once()
                logger.info("Monitoring cycle finished. scanned=%s", len(results))
            except Exception:
                logger.exception("Monitoring cycle failed")
            await asyncio.sleep(settings.monitor_interval_seconds)
    finally:
        await bot.session.close()
        await scraper.close()
        await db.dispose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
