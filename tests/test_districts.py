from goszdrav_bot.core.districts import DISTRICT_API_ID_BY_CODE


def test_nevskiy_maps_to_official_api_id() -> None:
    assert DISTRICT_API_ID_BY_CODE["nevskiy"] == "12"
