from goszdrav_bot.bot.commands import build_bot_commands


def test_build_bot_commands_contains_minimal_menu() -> None:
    commands = build_bot_commands()

    assert [item.command for item in commands] == ["start", "profile"]

