import pytest

from falyx.console import print_error
from falyx.exceptions import CommandArgumentError, MissingValueError
from falyx.parser import CommandArgumentParser


async def test_missing_value_error_has_user_facing_message():
    parser = CommandArgumentParser()
    parser.add_argument("--pair", type=int, nargs=2)

    with pytest.raises(MissingValueError) as exc:
        await parser.parse_args(["--pair", "1"])

    assert "pair" in str(exc.value)
    assert "expected" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_missing_value_error_for_fixed_nargs_has_message_and_hint():
    parser = CommandArgumentParser()
    parser.add_argument("--pair", type=int, nargs=2)

    with pytest.raises(MissingValueError) as exc:
        await parser.parse_args(["--pair", "1"])

    error = exc.value

    assert str(error) == "missing values for '--pair': expected 2, got 1"
    assert error.hint == "provide 2 values for '--pair'."
    assert error.show_short_usage is True
    assert error.dest == "pair"


@pytest.mark.asyncio
async def test_missing_value_error_for_plus_nargs_has_message_and_hint():
    parser = CommandArgumentParser()
    parser.add_argument("--items", nargs="+")

    with pytest.raises(MissingValueError) as exc:
        await parser.parse_args(["--items"])

    error = exc.value

    assert str(error) == "missing value for '--items'"
    assert error.hint == "provide one or more values for '--items'."


def test_print_error_uses_exception_hint(monkeypatch) -> None:
    printed: list[str] = []

    class FakeConsole:
        def print(self, value):
            printed.append(value)

    monkeypatch.setattr("falyx.console.error_console", FakeConsole())

    error = CommandArgumentError(
        "invalid command argument",
        hint="use --help to see available options",
    )

    print_error(error)

    assert any("error:" in line for line in printed)
    assert any("invalid command argument" in line for line in printed)
    assert any("hint:" in line for line in printed)
    assert any("use --help to see available options" in line for line in printed)
