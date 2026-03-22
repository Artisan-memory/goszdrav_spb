from __future__ import annotations

from pydantic import BaseModel, Field


class DistrictOption(BaseModel):
    code: str
    title: str


class OrganizationOption(BaseModel):
    external_id: str | None = None
    label: str
    address: str | None = None
    phone: str | None = None
    category: str | None = None


class SpecialtyOption(BaseModel):
    external_id: str | None = None
    label: str
    available_slots: int | None = None


class ScheduleDayPreview(BaseModel):
    title: str
    summary: str | None = None
    slot_times: list[str] = Field(default_factory=list)
    has_slots: bool = False
    missing_info: bool = False


class DoctorOption(BaseModel):
    external_id: str | None = None
    label: str
    available_slots: int | None = None
    has_schedule_button: bool = False
    preview_days: list[ScheduleDayPreview] = Field(default_factory=list)


class CalendarDayOption(BaseModel):
    day_number: str
    label: str | None = None
    is_available: bool = False
    is_selected: bool = False


class AppointmentSlotOption(BaseModel):
    time: str
    status: str | None = None
    address: str | None = None


class DoctorScheduleSnapshot(BaseModel):
    page_url: str | None = None
    month_label: str | None = None
    preview_days: list[ScheduleDayPreview] = Field(default_factory=list)
    calendar_days: list[CalendarDayOption] = Field(default_factory=list)
    slots: list[AppointmentSlotOption] = Field(default_factory=list)
