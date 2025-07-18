import pytest

from falyx.parser.command_argument_parser import CommandArgumentParser


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_tokens, expected",
    [
        ([""], ["--help", "--tag", "-h"]),
        (["--ta"], ["--tag"]),
        (["--tag"], ["analytics", "build"]),
    ],
)
async def test_suggest_next(input_tokens, expected):
    parser = CommandArgumentParser(...)
    parser.add_argument("--tag", choices=["analytics", "build"])
    assert sorted(parser.suggest_next(input_tokens)) == sorted(expected)
