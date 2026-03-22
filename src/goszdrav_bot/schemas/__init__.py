from goszdrav_bot.schemas.catalog import (
    AppointmentSlotOption,
    CalendarDayOption,
    DistrictOption,
    DoctorOption,
    DoctorScheduleSnapshot,
    OrganizationOption,
    ScheduleDayPreview,
    SpecialtyOption,
)
from goszdrav_bot.schemas.profile import ProfilePatch, ProfileView, TelegramIdentity
from goszdrav_bot.schemas.watch import (
    BookingAttemptView,
    ScrapeEventView,
    WatchTargetCreate,
    WatchTargetUpdate,
    WatchTargetView,
    WatchScanResultView,
)

__all__ = [
    "AppointmentSlotOption",
    "CalendarDayOption",
    "DistrictOption",
    "DoctorOption",
    "DoctorScheduleSnapshot",
    "OrganizationOption",
    "ProfilePatch",
    "ProfileView",
    "ScheduleDayPreview",
    "SpecialtyOption",
    "TelegramIdentity",
    "BookingAttemptView",
    "ScrapeEventView",
    "WatchTargetCreate",
    "WatchTargetUpdate",
    "WatchTargetView",
    "WatchScanResultView",
]
