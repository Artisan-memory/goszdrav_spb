from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from goszdrav_bot.config import Settings
from goszdrav_bot.db.models import BookingAttempt, ScrapeEvent, WatchTarget
from goszdrav_bot.scraper.service import AsyncGorzdravScraper
from goszdrav_bot.services.crypto import FieldCipher
from goszdrav_bot.services.profile import ProfileService
from goszdrav_bot.services.watch_targets import WatchTargetService
from goszdrav_bot.schemas.watch import BOOKING_STRATEGY_DEFAULT, BOOKING_STRATEGY_LABELS, BookingStrategy


class MonitoringService:
    def __init__(
        self,
        session,
        *,
        scraper: AsyncGorzdravScraper,
        cipher: FieldCipher,
        settings: Settings,
    ) -> None:
        self.session = session
        self.scraper = scraper
        self.cipher = cipher
        self.settings = settings
        self.watch_service = WatchTargetService(session)
        self.profile_service = ProfileService(session, cipher)

    async def scan_target(
        self,
        target: WatchTarget,
        *,
        bot: Bot | None = None,
        send_notification: bool = False,
        allow_booking: bool = True,
    ):
        profile = self.profile_service.profile_from_user(target.user)
        try:
            if target.doctor_label:
                result = await self._scan_specific_doctor(target)
            else:
                result = await self._scan_any_doctor(target)
        except Exception as exc:
            event = await self.watch_service.record_event(
                target,
                status="error",
                slots_count=0,
                result_url=None,
                summary=f"Ошибка сканирования: {exc}",
                payload_json={"error": str(exc)},
            )
            return self.watch_service.to_scan_result(target, event, notification_sent=False)

        event = await self.watch_service.record_event(
            target,
            status=result["status"],
            slots_count=result["slots_count"],
            result_url=result["result_url"],
            summary=result["summary"],
            payload_json=result["payload_json"],
        )

        booking_attempt = None
        if allow_booking and result["slots_count"] and target.mode == "autobook":
            try:
                booking_attempt = await self._attempt_booking(target, event, profile, result)
            except Exception as exc:
                booking_attempt = await self.watch_service.create_booking_attempt(
                    target,
                    event,
                    status="error",
                    slot_time=None,
                    direct_url=result["result_url"],
                    details=f"Ошибка автозаписи: {exc}",
                )

        notification_sent = False
        if send_notification and bot and result["slots_count"]:
            notification_sent = await self._notify_if_needed(bot, target, result)
            if booking_attempt is not None:
                await self._notify_booking_result_if_needed(bot, target, booking_attempt)

        return self.watch_service.to_scan_result(
            target,
            event,
            booking_attempt=booking_attempt,
            notification_sent=notification_sent,
        )

    async def _scan_specific_doctor(self, target: WatchTarget) -> dict:
        strategy = self._strategy_for_target(target)
        schedule = await self.scraper.get_doctor_schedule(
            district_key=target.district_code,
            organization_label=target.organization_label,
            specialty_label=target.specialty_label,
            doctor_label=target.doctor_label or "",
            organization_external_id=target.organization_external_id,
            specialty_external_id=target.specialty_external_id,
            doctor_external_id=target.doctor_external_id,
        )
        slots = schedule.get("slots", [])
        slots_count = len(slots)
        preferred_slot, strategy_context = self._pick_preferred_slot(slots, strategy)
        slot_preview = ", ".join(item["time"] for item in slots[:5]) if slots else "Номерков пока нет."
        summary = (
            f"{target.specialty_label} -> {target.doctor_label}: {slots_count} номерков. {slot_preview}"
        )
        return {
            "status": "slots_found" if slots_count else "no_slots",
            "slots_count": slots_count,
            "result_url": schedule.get("page_url"),
            "summary": summary,
            "payload_json": {"schedule": schedule},
            "preferred_slot_time": preferred_slot.get("time") if preferred_slot else None,
            "strategy_context": strategy_context,
            "resolved_doctor_label": target.doctor_label,
            "resolved_doctor_external_id": target.doctor_external_id,
        }

    async def _scan_any_doctor(self, target: WatchTarget) -> dict:
        strategy = self._strategy_for_target(target)
        doctors = await self.scraper.list_doctors(
            district_key=target.district_code,
            organization_label=target.organization_label,
            specialty_label=target.specialty_label,
            organization_external_id=target.organization_external_id,
            specialty_external_id=target.specialty_external_id,
        )
        available = [item for item in doctors if (item.get("available_slots") or 0) > 0]
        total_slots = sum(item.get("available_slots") or 0 for item in available)
        result_url = self.settings.gorzdrav_base_url
        resolved_doctor_label = None
        resolved_doctor_external_id = None
        preferred_slot_time = None
        strategy_context = self._empty_strategy_context(strategy)
        payload_json: dict = {"doctors": doctors}
        if available:
            candidates = await self._collect_any_doctor_candidates(target, available, strategy)
            if candidates:
                total_slots = sum(candidate["slots_count"] for candidate in candidates)
                best_candidate = min(candidates, key=self._candidate_sort_key)
                resolved_doctor_label = best_candidate["doctor"]["label"]
                resolved_doctor_external_id = best_candidate["doctor"].get("external_id")
                preferred_slot_time = best_candidate["preferred_slot"].get("time")
                strategy_context = best_candidate["strategy_context"]
                payload_json["schedule"] = best_candidate["schedule"]
                payload_json["best_candidate"] = {
                    "doctor_label": resolved_doctor_label,
                    "doctor_external_id": resolved_doctor_external_id,
                    "slot_time": preferred_slot_time,
                    "slots_count": best_candidate["slots_count"],
                    "booking_strategy": strategy_context["requested"],
                    "effective_booking_strategy": strategy_context["effective"],
                    "strategy_fallback_used": strategy_context["fallback_used"],
                }
                result_url = best_candidate["schedule"].get("page_url") or result_url
                preview = ", ".join(
                    f"{candidate['doctor']['label']} ({candidate['slots_count']})"
                    for candidate in candidates[:5]
                )
                summary = (
                    f"{target.specialty_label}: найдены номерки у врачей {preview}. "
                    f"Приоритет автозаписи: {resolved_doctor_label} -> {preferred_slot_time} "
                    f"({self._describe_booking_strategy(strategy_context['requested'])})"
                )
            else:
                first_available = available[0]
                resolved_doctor_label = first_available["label"]
                resolved_doctor_external_id = first_available.get("external_id")
                preview = ", ".join(
                    f"{item['label']} ({item.get('available_slots') or 0})" for item in available[:5]
                )
                summary = f"{target.specialty_label}: найдены номерки у врачей {preview}"
        else:
            summary = f"{target.specialty_label}: номерков пока нет."

        return {
            "status": "slots_found" if total_slots else "no_slots",
            "slots_count": total_slots,
            "result_url": result_url,
            "summary": summary,
            "payload_json": payload_json,
            "resolved_doctor_label": resolved_doctor_label,
            "resolved_doctor_external_id": resolved_doctor_external_id,
            "preferred_slot_time": preferred_slot_time,
            "strategy_context": strategy_context,
        }

    async def _attempt_booking(
        self,
        target: WatchTarget,
        event: ScrapeEvent,
        profile,
        result: dict,
    ) -> BookingAttempt:
        booking_doctor_label = target.doctor_label or result.get("resolved_doctor_label")
        if not booking_doctor_label:
            return await self.watch_service.create_booking_attempt(
                target,
                event,
                status="skipped",
                slot_time=None,
                direct_url=event.result_url,
                details="Автозапись пропущена: не удалось определить врача со свободными слотами.",
            )

        booking = await self.scraper.attempt_book_first_available_slot(
            district_key=target.district_code,
            organization_label=target.organization_label,
            specialty_label=target.specialty_label,
            doctor_label=booking_doctor_label,
            full_name=profile.full_name,
            birth_date=profile.birth_date.isoformat() if profile.birth_date else None,
            email=str(profile.email) if profile.email else None,
            preferred_slot_time=result.get("preferred_slot_time"),
        )
        details = booking.get("details")
        strategy_note = self._build_strategy_note(result.get("strategy_context"))
        if not target.doctor_label:
            prefix = f"Для автозаписи выбран врач по приоритету слота: {booking_doctor_label}. {strategy_note}"
            details = f"{prefix} {details}".strip() if details else prefix
        elif strategy_note not in (details or ""):
            details = f"{strategy_note} {details}".strip() if details else strategy_note
        return await self.watch_service.create_booking_attempt(
            target,
            event,
            status=booking["status"],
            slot_time=booking.get("slot_time"),
            direct_url=booking.get("direct_url"),
            details=details,
        )

    async def _collect_any_doctor_candidates(
        self,
        target: WatchTarget,
        doctors: list[dict],
        strategy: BookingStrategy,
    ) -> list[dict]:
        tasks = [
            self._fetch_doctor_candidate(target, doctor, strategy)
            for doctor in doctors
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [item for item in results if isinstance(item, dict)]

    async def _fetch_doctor_candidate(
        self,
        target: WatchTarget,
        doctor: dict,
        strategy: BookingStrategy,
    ) -> dict | None:
        schedule = await self.scraper.get_doctor_schedule(
            district_key=target.district_code,
            organization_label=target.organization_label,
            specialty_label=target.specialty_label,
            doctor_label=doctor["label"],
            organization_external_id=target.organization_external_id,
            specialty_external_id=target.specialty_external_id,
            doctor_external_id=doctor.get("external_id"),
        )
        slots = schedule.get("slots", [])
        preferred_slot, strategy_context = self._pick_preferred_slot(slots, strategy)
        if not slots or not preferred_slot:
            return None
        return {
            "doctor": doctor,
            "schedule": schedule,
            "slots_count": len(slots),
            "preferred_slot": preferred_slot,
            "sort_key": self._slot_priority(
                preferred_slot.get("time"),
                strategy_context["effective"],
            ),
            "strategy_context": strategy_context,
        }

    @classmethod
    def _candidate_sort_key(cls, candidate: dict) -> tuple[int, int]:
        return candidate["sort_key"]

    @classmethod
    def _pick_preferred_slot(
        cls,
        slots: list[dict],
        strategy: BookingStrategy,
    ) -> tuple[dict | None, dict]:
        normalized_strategy = cls._normalize_booking_strategy(strategy)
        context = cls._empty_strategy_context(normalized_strategy)
        if not slots:
            return None, context

        candidate_slots = cls._filter_slots_for_strategy(slots, normalized_strategy)
        if not candidate_slots and normalized_strategy in {"morning_only", "evening_only"}:
            candidate_slots = slots
            context["effective"] = BOOKING_STRATEGY_DEFAULT
            context["fallback_used"] = True

        parsed_slots: list[tuple[int, int, dict]] = []
        for slot in candidate_slots:
            priority = cls._slot_priority(slot.get("time"), context["effective"])
            if priority[0] == 10**12:
                continue
            parsed_slots.append((priority[0], priority[1], slot))
        if parsed_slots:
            parsed_slots.sort(key=lambda item: (item[0], item[1]))
            return parsed_slots[0][2], context
        return candidate_slots[0], context

    @classmethod
    def _slot_priority(cls, raw_value: str | None, strategy: BookingStrategy) -> tuple[int, int]:
        parsed = cls._parse_slot_datetime(raw_value)
        if parsed is None:
            return 10**12, 0
        ordinal = parsed.date().toordinal()
        minutes = parsed.hour * 60 + parsed.minute
        normalized_strategy = cls._normalize_booking_strategy(strategy)
        if normalized_strategy == "nearest_date_earliest_time":
            return ordinal, minutes
        return ordinal, -minutes

    @staticmethod
    def _parse_slot_datetime(raw_value: str | None) -> datetime | None:
        if not raw_value:
            return None
        text = " ".join(str(raw_value).split())
        for pattern in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M", "%d.%m.%Y", "%Y-%m-%d", "%H:%M"):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
        return None

    @classmethod
    def _filter_slots_for_strategy(
        cls,
        slots: list[dict],
        strategy: BookingStrategy,
    ) -> list[dict]:
        normalized_strategy = cls._normalize_booking_strategy(strategy)
        if normalized_strategy == "morning_only":
            return [
                slot for slot in slots
                if (parsed := cls._parse_slot_datetime(slot.get("time"))) is not None and parsed.hour < 12
            ]
        if normalized_strategy == "evening_only":
            return [
                slot for slot in slots
                if (parsed := cls._parse_slot_datetime(slot.get("time"))) is not None and parsed.hour >= 16
            ]
        return slots

    @classmethod
    def _normalize_booking_strategy(cls, strategy: str | None) -> BookingStrategy:
        if strategy in BOOKING_STRATEGY_LABELS:
            return strategy
        return BOOKING_STRATEGY_DEFAULT

    @classmethod
    def _describe_booking_strategy(cls, strategy: str | None) -> str:
        normalized_strategy = cls._normalize_booking_strategy(strategy)
        return BOOKING_STRATEGY_LABELS[normalized_strategy]

    @classmethod
    def _empty_strategy_context(cls, strategy: str | None) -> dict[str, str | bool]:
        normalized_strategy = cls._normalize_booking_strategy(strategy)
        return {
            "requested": normalized_strategy,
            "effective": normalized_strategy,
            "fallback_used": False,
        }

    @classmethod
    def _build_strategy_note(cls, strategy_context: dict | None) -> str:
        context = strategy_context or cls._empty_strategy_context(BOOKING_STRATEGY_DEFAULT)
        requested_strategy = cls._normalize_booking_strategy(context.get("requested"))
        effective_strategy = cls._normalize_booking_strategy(context.get("effective"))
        requested_label = cls._describe_booking_strategy(requested_strategy)
        if context.get("fallback_used") and effective_strategy != requested_strategy:
            effective_label = cls._describe_booking_strategy(effective_strategy)
            return (
                f"Стратегия выбора талона: {requested_label}. "
                f"Подходящих слотов не нашлось, использован запасной вариант: {effective_label}."
            )
        return f"Стратегия выбора талона: {requested_label}."

    @staticmethod
    def _strategy_for_target(target: WatchTarget) -> BookingStrategy:
        strategy = getattr(target, "booking_strategy", None)
        if strategy in BOOKING_STRATEGY_LABELS:
            return strategy
        return BOOKING_STRATEGY_DEFAULT

    async def _notify_if_needed(self, bot: Bot, target: WatchTarget, result: dict) -> bool:
        fingerprint = self._fingerprint(target.id, result["summary"], result["result_url"], result["slots_count"])
        existing = await self.watch_service.get_recent_notification_by_fingerprint(fingerprint)
        now = datetime.now(timezone.utc)
        if existing and existing.sent_at >= now - timedelta(seconds=self.settings.notify_cooldown_seconds):
            return False

        message_text = self._build_message(target, result)
        reply_markup = None
        if result["result_url"]:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Открыть расписание", url=result["result_url"])]
                ]
            )
        try:
            await bot.send_message(
                chat_id=target.user.telegram_id,
                text=message_text,
                reply_markup=reply_markup,
                disable_web_page_preview=False,
            )
        except Exception:
            return False
        await self.watch_service.record_notification(
            target,
            kind="slots_found",
            fingerprint=fingerprint,
            message_text=message_text,
            direct_url=result["result_url"],
        )
        return True

    @staticmethod
    def _fingerprint(target_id: int, summary: str | None, result_url: str | None, slots_count: int | None) -> str:
        raw = f"{target_id}|{summary or ''}|{result_url or ''}|{slots_count or 0}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]

    @staticmethod
    def _build_message(target: WatchTarget, result: dict) -> str:
        mode_title = "Автозапись" if target.mode == "autobook" else "Уведомление"
        doctor_title = result.get("resolved_doctor_label") or target.doctor_label or "Любой врач"
        lines = [
            f"<b>{mode_title}: найден номерок</b>",
            f"Поликлиника: {target.organization_label}",
            f"Специальность: {target.specialty_label}",
            f"Врач: {doctor_title}",
        ]
        if target.mode == "autobook":
            lines.append(
                f"Стратегия: {MonitoringService._describe_booking_strategy(getattr(target, 'booking_strategy', None))}"
            )
        lines.extend(
            [
            f"Сводка: {result['summary']}",
            ]
        )
        if result["result_url"]:
            lines.append("")
            lines.append(f"Ссылка: {result['result_url']}")
        return "\n".join(lines)

    async def _notify_booking_result_if_needed(
        self,
        bot: Bot,
        target: WatchTarget,
        booking_attempt: BookingAttempt,
    ) -> bool:
        fingerprint = self._fingerprint(
            target.id,
            f"booking:{booking_attempt.status}:{booking_attempt.slot_time or ''}",
            booking_attempt.direct_url,
            0,
        )
        existing = await self.watch_service.get_recent_notification_by_fingerprint(fingerprint)
        now = datetime.now(timezone.utc)
        if existing and existing.sent_at >= now - timedelta(seconds=self.settings.notify_cooldown_seconds):
            return False

        lines = [
            "<b>Результат автозаписи</b>",
            f"Поликлиника: {target.organization_label}",
            f"Специальность: {target.specialty_label}",
            f"Врач: {target.doctor_label or 'Выбран автоматически по приоритету слота'}",
            f"Стратегия: {self._describe_booking_strategy(getattr(target, 'booking_strategy', None))}",
            f"Статус попытки: {booking_attempt.status}",
        ]
        if booking_attempt.slot_time:
            lines.append(f"Талон: {booking_attempt.slot_time}")
        if booking_attempt.details:
            lines.append(f"Детали: {booking_attempt.details[:500]}")
        if booking_attempt.direct_url:
            lines.append("")
            lines.append(f"Ссылка: {booking_attempt.direct_url}")

        reply_markup = None
        if booking_attempt.direct_url:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Открыть шаг записи", url=booking_attempt.direct_url)]
                ]
            )

        message_text = "\n".join(lines)
        try:
            await bot.send_message(
                chat_id=target.user.telegram_id,
                text=message_text,
                reply_markup=reply_markup,
                disable_web_page_preview=False,
            )
        except Exception:
            return False
        await self.watch_service.record_notification(
            target,
            kind="booking_result",
            fingerprint=fingerprint,
            message_text=message_text,
            direct_url=booking_attempt.direct_url,
        )
        return True
