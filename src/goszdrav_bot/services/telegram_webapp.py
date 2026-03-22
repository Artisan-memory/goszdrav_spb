from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from goszdrav_bot.schemas.profile import TelegramIdentity


class TelegramWebAppInitDataError(ValueError):
    pass


def parse_and_validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86_400,
) -> TelegramIdentity:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise TelegramWebAppInitDataError("Telegram init data hash is missing.")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_hash, calculated_hash):
        raise TelegramWebAppInitDataError("Telegram init data signature is invalid.")

    auth_date = parsed.get("auth_date")
    if auth_date:
        age_seconds = int(datetime.now(timezone.utc).timestamp()) - int(auth_date)
        if age_seconds > max_age_seconds:
            raise TelegramWebAppInitDataError("Telegram init data expired.")

    raw_user = parsed.get("user")
    if not raw_user:
        raise TelegramWebAppInitDataError("Telegram init data does not contain a user payload.")

    user_data = json.loads(raw_user)
    return TelegramIdentity(
        telegram_id=user_data["id"],
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        language_code=user_data.get("language_code"),
    )
