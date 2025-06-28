import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parser import CommandArgumentParser


@pytest.mark.asyncio
async def test_parse_negative_integer():
    parser = CommandArgumentParser()
    parser.add_argument("--number", type=int, required=True, help="A negative integer")
    args = await parser.parse_args(["--number", "-42"])
    assert args["number"] == -42


@pytest.mark.asyncio
async def test_parse_negative_float():
    parser = CommandArgumentParser()
    parser.add_argument("--value", type=float, required=True, help="A negative float")
    args = await parser.parse_args(["--value", "-3.14"])
    assert args["value"] == -3.14


def test_parse_number_flag():
    parser = CommandArgumentParser()
    with pytest.raises(CommandArgumentError):
        parser.add_argument("-1", type=int, required=True, help="A negative number flag")
