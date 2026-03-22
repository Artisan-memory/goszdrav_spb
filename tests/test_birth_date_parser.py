from datetime import date

from goszdrav_bot.bot.handlers.profile import format_birth_date, parse_birth_date_input


def test_parse_birth_date_input_accepts_russian_format() -> None:
    assert parse_birth_date_input("16.06.2000") == date(2000, 6, 16)


def test_parse_birth_date_input_accepts_iso_format() -> None:
    assert parse_birth_date_input("2000-06-16") == date(2000, 6, 16)


def test_format_birth_date_returns_russian_style() -> None:
    assert format_birth_date(date(2000, 6, 16)) == "16.06.2000"
