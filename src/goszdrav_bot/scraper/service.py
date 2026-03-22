from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from goszdrav_bot.config import Settings
from goszdrav_bot.core.districts import DISTRICT_BY_CODE, DISTRICT_CODE_BY_TITLE
from goszdrav_bot.scraper.api_client import GorzdravApiClient
from goszdrav_bot.scraper.selenium_client import GorzdravSeleniumScraper


class AsyncGorzdravScraper:
    def __init__(self, settings: Settings) -> None:
        self._semaphore = asyncio.Semaphore(settings.scraper_max_workers)
        self._executor = ThreadPoolExecutor(
            max_workers=settings.scraper_max_workers,
            thread_name_prefix="gorzdrav-scraper",
        )
        self._booking_client = GorzdravSeleniumScraper(
            base_url=settings.gorzdrav_base_url,
            headless=settings.selenium_headless,
            timeout_seconds=settings.selenium_timeout_seconds,
            chrome_binary=settings.selenium_chrome_binary,
        )
        self._api_client = GorzdravApiClient(
            api_base_url=settings.gorzdrav_api_base_url,
            public_base_url=settings.gorzdrav_base_url,
            timeout_seconds=settings.selenium_timeout_seconds,
        )

    async def list_organizations(self, district_key: str, query: str | None = None) -> list[dict]:
        async with self._semaphore:
            return await self._api_client.list_organizations(district_key, query)

    async def list_specialties(
        self,
        district_key: str,
        organization_label: str,
        *,
        organization_external_id: str | None = None,
    ) -> list[dict]:
        async with self._semaphore:
            return await self._api_client.list_specialties(
                district_key,
                organization_label,
                organization_external_id=organization_external_id,
            )

    async def list_doctors(
        self,
        district_key: str,
        organization_label: str,
        specialty_label: str,
        *,
        organization_external_id: str | None = None,
        specialty_external_id: str | None = None,
    ) -> list[dict]:
        async with self._semaphore:
            return await self._api_client.list_doctors(
                district_key,
                organization_label,
                specialty_label,
                organization_external_id=organization_external_id,
                specialty_external_id=specialty_external_id,
            )

    async def get_doctor_schedule(
        self,
        district_key: str,
        organization_label: str,
        specialty_label: str,
        doctor_label: str,
        *,
        organization_external_id: str | None = None,
        specialty_external_id: str | None = None,
        doctor_external_id: str | None = None,
    ) -> dict:
        async with self._semaphore:
            return await self._api_client.get_doctor_schedule(
                district_key,
                organization_label,
                specialty_label,
                doctor_label,
                organization_external_id=organization_external_id,
                specialty_external_id=specialty_external_id,
                doctor_external_id=doctor_external_id,
            )

    async def attempt_book_first_available_slot(
        self,
        district_key: str,
        organization_label: str,
        specialty_label: str,
        doctor_label: str,
        *,
        full_name: str | None,
        birth_date: str | None,
        email: str | None,
        preferred_slot_time: str | None = None,
    ) -> dict:
        return await self._run_blocking(
            self._booking_client.attempt_book_first_available_slot,
            self._normalize_district_title(district_key),
            organization_label,
            specialty_label,
            doctor_label,
            full_name=full_name,
            birth_date=birth_date,
            email=email,
            preferred_slot_time=preferred_slot_time,
        )

    async def close(self) -> None:
        await self._api_client.close()
        await asyncio.to_thread(
            partial(self._executor.shutdown, wait=True, cancel_futures=True)
        )

    async def _run_blocking(self, func, *args, **kwargs):
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, partial(func, *args, **kwargs))

    @staticmethod
    def _normalize_district_title(district_key: str) -> str:
        if district_key in DISTRICT_BY_CODE:
            return DISTRICT_BY_CODE[district_key]
        if district_key in DISTRICT_CODE_BY_TITLE:
            return district_key

        normalized = " ".join((district_key or "").lower().split())
        for code, title in DISTRICT_BY_CODE.items():
            if normalized == code or normalized == " ".join(title.lower().split()):
                return title
        return district_key
