from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WatchMode = Literal["notify", "autobook"]
BookingStrategy = Literal[
    "nearest_date_latest_time",
    "nearest_date_earliest_time",
    "morning_only",
    "evening_only",
]

BOOKING_STRATEGY_DEFAULT: BookingStrategy = "nearest_date_latest_time"
BOOKING_STRATEGY_LABELS: dict[BookingStrategy, str] = {
    "nearest_date_latest_time": "Ближайшая дата, позднее время",
    "nearest_date_earliest_time": "Ближайшая дата, раннее время",
    "morning_only": "Только утро",
    "evening_only": "Только вечер",
}


class WatchTargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specialty_external_id: str | None = Field(default=None, max_length=128)
    specialty_label: str = Field(min_length=2, max_length=255)
    doctor_external_id: str | None = Field(default=None, max_length=128)
    doctor_label: str | None = Field(default=None, max_length=255)
    mode: WatchMode = "notify"
    booking_strategy: BookingStrategy = BOOKING_STRATEGY_DEFAULT

    @field_validator("specialty_external_id", "specialty_label", "doctor_external_id", "doctor_label")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = " ".join(value.split()).strip()
        return normalized or None


class WatchTargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    mode: WatchMode | None = None
    booking_strategy: BookingStrategy | None = None


class WatchTargetView(BaseModel):
    id: int
    district_code: str
    organization_external_id: str | None = None
    organization_label: str
    specialty_external_id: str | None = None
    specialty_label: str
    doctor_external_id: str | None = None
    doctor_label: str | None = None
    mode: WatchMode
    booking_strategy: BookingStrategy
    is_active: bool
    latest_result_status: str | None = None
    latest_result_summary: str | None = None
    latest_result_url: str | None = None
    last_seen_slots_count: int | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ScrapeEventView(BaseModel):
    id: int
    status: str
    slots_count: int | None = None
    result_url: str | None = None
    summary: str | None = None
    happened_at: datetime


class BookingAttemptView(BaseModel):
    id: int
    status: str
    slot_time: str | None = None
    direct_url: str | None = None
    details: str | None = None
    created_at: datetime
    updated_at: datetime


class WatchScanResultView(BaseModel):
    target: WatchTargetView
    event: ScrapeEventView
    booking_attempt: BookingAttemptView | None = None
    notification_sent: bool = False
