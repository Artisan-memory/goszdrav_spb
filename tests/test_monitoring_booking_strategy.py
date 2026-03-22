from goszdrav_bot.schemas.watch import BOOKING_STRATEGY_DEFAULT, WatchTargetCreate
from goszdrav_bot.services.monitoring import MonitoringService


def test_watch_target_create_uses_default_booking_strategy() -> None:
    payload = WatchTargetCreate(specialty_label="Детский хирург")

    assert payload.booking_strategy == BOOKING_STRATEGY_DEFAULT


def test_nearest_date_latest_time_prefers_later_time_on_same_day() -> None:
    slot, context = MonitoringService._pick_preferred_slot(
        [
            {"time": "24.03.2026 08:00"},
            {"time": "24.03.2026 09:15"},
            {"time": "26.03.2026 14:15"},
        ],
        "nearest_date_latest_time",
    )

    assert slot == {"time": "24.03.2026 09:15"}
    assert context["requested"] == "nearest_date_latest_time"
    assert context["fallback_used"] is False


def test_nearest_date_earliest_time_prefers_earlier_time_on_same_day() -> None:
    slot, context = MonitoringService._pick_preferred_slot(
        [
            {"time": "24.03.2026 08:00"},
            {"time": "24.03.2026 09:15"},
            {"time": "26.03.2026 14:15"},
        ],
        "nearest_date_earliest_time",
    )

    assert slot == {"time": "24.03.2026 08:00"}
    assert context["requested"] == "nearest_date_earliest_time"
    assert context["fallback_used"] is False


def test_evening_only_falls_back_to_default_strategy_when_needed() -> None:
    slot, context = MonitoringService._pick_preferred_slot(
        [
            {"time": "24.03.2026 08:00"},
            {"time": "24.03.2026 09:15"},
            {"time": "26.03.2026 14:15"},
        ],
        "evening_only",
    )

    assert slot == {"time": "24.03.2026 09:15"}
    assert context["requested"] == "evening_only"
    assert context["effective"] == BOOKING_STRATEGY_DEFAULT
    assert context["fallback_used"] is True
