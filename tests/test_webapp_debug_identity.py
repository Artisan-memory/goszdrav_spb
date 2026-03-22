from types import SimpleNamespace

from goszdrav_bot.api.routes.profile import get_debug_telegram_id


def make_request(*, dev_mode: bool, debug_id=None, bot_admin_ids=None, headers=None, query_params=None):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    webapp_dev_mode=dev_mode,
                    webapp_dev_telegram_id=debug_id,
                    bot_admin_ids=bot_admin_ids or [],
                )
            )
        ),
        headers=headers or {},
        query_params=query_params or {},
    )


def test_debug_identity_uses_explicit_setting() -> None:
    request = make_request(dev_mode=True, debug_id=123456)
    assert get_debug_telegram_id(request) == 123456


def test_debug_identity_falls_back_to_first_admin() -> None:
    request = make_request(dev_mode=True, bot_admin_ids=[999888777])
    assert get_debug_telegram_id(request) == 999888777


def test_debug_identity_uses_header_override() -> None:
    request = make_request(
        dev_mode=True,
        debug_id=123456,
        headers={"X-Debug-Telegram-Id": "555444333"},
    )
    assert get_debug_telegram_id(request) == 555444333
