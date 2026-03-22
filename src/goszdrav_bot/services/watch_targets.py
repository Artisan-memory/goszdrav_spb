from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from goszdrav_bot.db.models import BookingAttempt, ScrapeEvent, TelegramUser, UserNotification, WatchTarget
from goszdrav_bot.schemas.profile import ProfileView
from goszdrav_bot.schemas.watch import (
    BOOKING_STRATEGY_DEFAULT,
    BookingAttemptView,
    ScrapeEventView,
    WatchTargetCreate,
    WatchTargetUpdate,
    WatchTargetView,
    WatchScanResultView,
)


class WatchTargetService:
    def __init__(self, session) -> None:
        self.session = session

    async def list_for_user(self, telegram_id: int) -> list[WatchTargetView]:
        user = await self._get_user_with_targets(telegram_id)
        if user is None:
            return []
        return [self._to_view(item) for item in user.watch_targets]

    async def get_for_user(self, telegram_id: int, target_id: int) -> WatchTarget | None:
        result = await self.session.execute(
            select(WatchTarget)
            .options(selectinload(WatchTarget.user).selectinload(TelegramUser.profile))
            .join(TelegramUser, TelegramUser.id == WatchTarget.user_id)
            .where(TelegramUser.telegram_id == telegram_id, WatchTarget.id == target_id)
        )
        return result.scalar_one_or_none()

    async def create_for_user(
        self,
        user: TelegramUser,
        profile: ProfileView,
        payload: WatchTargetCreate,
    ) -> WatchTargetView:
        if not profile.district_code or not profile.organization_label:
            raise ValueError("Сначала заполните профиль: район и медорганизацию.")

        doctor_clause = (
            WatchTarget.doctor_label.is_(None)
            if payload.doctor_label is None
            else WatchTarget.doctor_label == payload.doctor_label
        )
        duplicate = await self.session.execute(
            select(WatchTarget).where(
                WatchTarget.user_id == user.id,
                WatchTarget.district_code == profile.district_code,
                WatchTarget.organization_label == profile.organization_label,
                WatchTarget.specialty_label == payload.specialty_label,
                doctor_clause,
                WatchTarget.mode == payload.mode,
                *(
                    [WatchTarget.booking_strategy == payload.booking_strategy]
                    if payload.mode == "autobook"
                    else []
                ),
            ).limit(1)
        )
        if duplicate.scalars().first() is not None:
            raise ValueError("Такое наблюдение уже существует.")

        target = WatchTarget(
            user_id=user.id,
            district_code=profile.district_code,
            organization_external_id=profile.organization_external_id,
            organization_label=profile.organization_label,
            specialty_external_id=payload.specialty_external_id,
            specialty_label=payload.specialty_label,
            doctor_external_id=payload.doctor_external_id,
            doctor_label=payload.doctor_label,
            mode=payload.mode,
            booking_strategy=payload.booking_strategy,
            is_active=True,
        )
        self.session.add(target)
        await self.session.flush()
        return self._to_view(target)

    async def update_for_user(
        self,
        telegram_id: int,
        target_id: int,
        payload: WatchTargetUpdate,
    ) -> WatchTargetView | None:
        target = await self.get_for_user(telegram_id, target_id)
        if target is None:
            return None

        data = payload.model_dump(exclude_unset=True)
        if "is_active" in data and data["is_active"] is not None:
            target.is_active = data["is_active"]
        if "mode" in data and data["mode"]:
            target.mode = data["mode"]
        if "booking_strategy" in data and data["booking_strategy"]:
            target.booking_strategy = data["booking_strategy"]

        await self.session.flush()
        return self._to_view(target)

    async def delete_for_user(self, telegram_id: int, target_id: int) -> bool:
        target = await self.get_for_user(telegram_id, target_id)
        if target is None:
            return False
        await self.session.delete(target)
        await self.session.flush()
        return True

    async def list_active_targets(self) -> list[WatchTarget]:
        result = await self.session.execute(
            select(WatchTarget)
            .options(selectinload(WatchTarget.user).selectinload(TelegramUser.profile))
            .where(WatchTarget.is_active.is_(True))
            .order_by(WatchTarget.id.asc())
        )
        return list(result.scalars().all())

    async def record_event(
        self,
        target: WatchTarget,
        *,
        status: str,
        slots_count: int | None,
        result_url: str | None,
        summary: str | None,
        payload_json: dict | None,
    ) -> ScrapeEvent:
        happened_at = datetime.now(timezone.utc)
        event = ScrapeEvent(
            watch_target_id=target.id,
            status=status,
            slots_count=slots_count,
            result_url=result_url,
            summary=summary,
            payload_json=payload_json,
            happened_at=happened_at,
        )
        self.session.add(event)
        target.latest_result_status = status
        target.latest_result_summary = summary
        target.latest_result_url = result_url
        target.last_seen_slots_count = slots_count
        target.last_checked_at = happened_at
        await self.session.flush()
        return event

    async def record_notification(
        self,
        target: WatchTarget,
        *,
        kind: str,
        fingerprint: str,
        message_text: str,
        direct_url: str | None,
    ) -> UserNotification:
        notification = UserNotification(
            watch_target_id=target.id,
            telegram_user_id=target.user_id,
            kind=kind,
            fingerprint=fingerprint,
            message_text=message_text,
            direct_url=direct_url,
        )
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def get_recent_notification_by_fingerprint(self, fingerprint: str) -> UserNotification | None:
        result = await self.session.execute(
            select(UserNotification)
            .where(UserNotification.fingerprint == fingerprint)
            .order_by(desc(UserNotification.sent_at))
            .limit(1)
        )
        return result.scalars().first()

    async def get_by_id(self, target_id: int) -> WatchTarget | None:
        result = await self.session.execute(
            select(WatchTarget)
            .options(selectinload(WatchTarget.user).selectinload(TelegramUser.profile))
            .where(WatchTarget.id == target_id)
        )
        return result.scalar_one_or_none()

    async def create_booking_attempt(
        self,
        target: WatchTarget,
        event: ScrapeEvent | None,
        *,
        status: str,
        slot_time: str | None,
        direct_url: str | None,
        details: str | None,
    ) -> BookingAttempt:
        attempt = BookingAttempt(
            watch_target_id=target.id,
            scrape_event_id=event.id if event else None,
            status=status,
            slot_time=slot_time,
            direct_url=direct_url,
            details=details,
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    def to_scan_result(
        self,
        target: WatchTarget,
        event: ScrapeEvent,
        *,
        booking_attempt: BookingAttempt | None = None,
        notification_sent: bool = False,
    ) -> WatchScanResultView:
        return WatchScanResultView(
            target=self._to_view(target),
            event=ScrapeEventView(
                id=event.id,
                status=event.status,
                slots_count=event.slots_count,
                result_url=event.result_url,
                summary=event.summary,
                happened_at=event.happened_at,
            ),
            booking_attempt=self._to_booking_view(booking_attempt) if booking_attempt else None,
            notification_sent=notification_sent,
        )

    async def _get_user_with_targets(self, telegram_id: int) -> TelegramUser | None:
        result = await self.session.execute(
            select(TelegramUser)
            .options(selectinload(TelegramUser.watch_targets))
            .where(TelegramUser.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _to_view(target: WatchTarget) -> WatchTargetView:
        return WatchTargetView(
            id=target.id,
            district_code=target.district_code,
            organization_external_id=target.organization_external_id,
            organization_label=target.organization_label,
            specialty_external_id=target.specialty_external_id,
            specialty_label=target.specialty_label,
            doctor_external_id=target.doctor_external_id,
            doctor_label=target.doctor_label,
            mode=target.mode,
            booking_strategy=target.booking_strategy or BOOKING_STRATEGY_DEFAULT,
            is_active=target.is_active,
            latest_result_status=target.latest_result_status,
            latest_result_summary=target.latest_result_summary,
            latest_result_url=target.latest_result_url,
            last_seen_slots_count=target.last_seen_slots_count,
            last_checked_at=target.last_checked_at,
            created_at=target.created_at,
            updated_at=target.updated_at,
        )

    @staticmethod
    def _to_booking_view(attempt: BookingAttempt) -> BookingAttemptView:
        return BookingAttemptView(
            id=attempt.id,
            status=attempt.status,
            slot_time=attempt.slot_time,
            direct_url=attempt.direct_url,
            details=attempt.details,
            created_at=attempt.created_at,
            updated_at=attempt.updated_at,
        )
