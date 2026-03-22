from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from goszdrav_bot.db.base import Base, utcnow


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TelegramUser(TimestampMixin, Base):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    profile: Mapped["UserProfile"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    watch_targets: Mapped[list["WatchTarget"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    notifications: Mapped[list["UserNotification"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id", ondelete="CASCADE"), primary_key=True)
    full_name_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    birth_date_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    district_code: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    organization_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    organization_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[TelegramUser] = relationship(back_populates="profile", lazy="selectin")


class WatchTarget(TimestampMixin, Base):
    __tablename__ = "watch_targets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True)
    district_code: Mapped[str] = mapped_column(String(64), index=True)
    organization_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    organization_label: Mapped[str] = mapped_column(String(255))
    specialty_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    specialty_label: Mapped[str] = mapped_column(String(255))
    doctor_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    doctor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="notify")
    booking_strategy: Mapped[str] = mapped_column(String(48), default="nearest_date_latest_time")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    latest_result_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latest_result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_result_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_seen_slots_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[TelegramUser] = relationship(back_populates="watch_targets", lazy="selectin")
    scrape_events: Mapped[list["ScrapeEvent"]] = relationship(
        back_populates="watch_target",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    notifications: Mapped[list["UserNotification"]] = relationship(
        back_populates="watch_target",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    booking_attempts: Mapped[list["BookingAttempt"]] = relationship(
        back_populates="watch_target",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ScrapeEvent(Base):
    __tablename__ = "scrape_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    watch_target_id: Mapped[int] = mapped_column(ForeignKey("watch_targets.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    slots_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    watch_target: Mapped[WatchTarget] = relationship(back_populates="scrape_events", lazy="selectin")
    booking_attempts: Mapped[list["BookingAttempt"]] = relationship(
        back_populates="scrape_event",
        lazy="selectin",
    )


class UserNotification(Base):
    __tablename__ = "user_notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    watch_target_id: Mapped[int] = mapped_column(ForeignKey("watch_targets.id", ondelete="CASCADE"), index=True)
    telegram_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    message_text: Mapped[str] = mapped_column(Text)
    direct_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    watch_target: Mapped[WatchTarget] = relationship(back_populates="notifications", lazy="selectin")
    user: Mapped[TelegramUser] = relationship(back_populates="notifications", lazy="selectin")


class BookingAttempt(TimestampMixin, Base):
    __tablename__ = "booking_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    watch_target_id: Mapped[int] = mapped_column(ForeignKey("watch_targets.id", ondelete="CASCADE"), index=True)
    scrape_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("scrape_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    slot_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    direct_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    watch_target: Mapped[WatchTarget] = relationship(back_populates="booking_attempts", lazy="selectin")
    scrape_event: Mapped[ScrapeEvent | None] = relationship(back_populates="booking_attempts", lazy="selectin")
