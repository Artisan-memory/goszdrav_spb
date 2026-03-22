from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OrganizationRecord:
    label: str
    external_id: str | None = None
    address: str | None = None
    phone: str | None = None
    category: str | None = None


@dataclass(slots=True)
class SpecialtyRecord:
    label: str
    external_id: str | None = None
    available_slots: int | None = None


@dataclass(slots=True)
class ScheduleDayRecord:
    title: str
    summary: str | None = None
    slot_times: list[str] = field(default_factory=list)
    has_slots: bool = False
    missing_info: bool = False


@dataclass(slots=True)
class DoctorRecord:
    label: str
    external_id: str | None = None
    available_slots: int | None = None
    has_schedule_button: bool = False
    preview_days: list[ScheduleDayRecord] = field(default_factory=list)


@dataclass(slots=True)
class CalendarDayRecord:
    day_number: str
    label: str | None = None
    is_available: bool = False
    is_selected: bool = False


@dataclass(slots=True)
class AppointmentSlotRecord:
    time: str
    status: str | None = None
    address: str | None = None


@dataclass(slots=True)
class DoctorScheduleRecord:
    page_url: str | None = None
    month_label: str | None = None
    preview_days: list[ScheduleDayRecord] = field(default_factory=list)
    calendar_days: list[CalendarDayRecord] = field(default_factory=list)
    slots: list[AppointmentSlotRecord] = field(default_factory=list)


@dataclass(slots=True)
class BookingResultRecord:
    status: str
    slot_time: str | None = None
    direct_url: str | None = None
    details: str | None = None
