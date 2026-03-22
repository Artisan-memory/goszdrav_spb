from __future__ import annotations

import asyncio

from aiogram import Bot

from goszdrav_bot.config import Settings
from goszdrav_bot.db.session import Database
from goszdrav_bot.scraper.service import AsyncGorzdravScraper
from goszdrav_bot.services.crypto import FieldCipher
from goszdrav_bot.services.monitoring import MonitoringService
from goszdrav_bot.services.watch_targets import WatchTargetService


class SlotMonitor:
    def __init__(
        self,
        *,
        db: Database,
        scraper: AsyncGorzdravScraper,
        cipher: FieldCipher,
        settings: Settings,
        bot: Bot,
    ) -> None:
        self.db = db
        self.scraper = scraper
        self.cipher = cipher
        self.settings = settings
        self.bot = bot

    async def scan_once(self) -> list[dict]:
        async with self.db.session() as session:
            watch_service = WatchTargetService(session)
            targets = await watch_service.list_active_targets()
            target_ids = [target.id for target in targets]

        results: list[dict] = []
        async with asyncio.TaskGroup() as task_group:
            tasks = [task_group.create_task(self._scan_target(target_id)) for target_id in target_ids]
        for task in tasks:
            results.append(task.result())
        return results

    async def _scan_target(self, target_id: int) -> dict:
        try:
            async with self.db.session() as session:
                watch_service = WatchTargetService(session)
                target = await watch_service.get_by_id(target_id)
                if target is None:
                    return {"target_id": target_id, "status": "missing"}
                monitoring = MonitoringService(
                    session,
                    scraper=self.scraper,
                    cipher=self.cipher,
                    settings=self.settings,
                )
                result = await monitoring.scan_target(
                    target,
                    bot=self.bot,
                    send_notification=True,
                    allow_booking=True,
                )
                return result.model_dump()
        except Exception as exc:
            return {"target_id": target_id, "status": "error", "error": str(exc)}
