import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parser import ArgumentAction, CommandArgumentParser


@pytest.mark.asyncio
async def test_nargs():
    """Test the nargs argument for command-line arguments."""
    parser = CommandArgumentParser()
    parser.add_argument(
        "-a",
        "--alpha",
        action=ArgumentAction.STORE,
        nargs=2,
        help="Alpha option with two arguments",
    )
    parser.add_argument(
        "-b",
        "--beta",
        action=ArgumentAction.STORE,
        nargs="+",
        help="Beta option with one or more arguments",
    )
    parser.add_argument(
        "-c",
        "--charlie",
        action=ArgumentAction.STORE,
        nargs="*",
        help="Charlie option with zero or more arguments",
    )

    # Test valid cases
    args = await parser.parse_args(["-a", "value1", "value2"])
    assert args["alpha"] == ["value1", "value2"]

    args = await parser.parse_args(["-b", "value1", "value2", "value3"])
    assert args["beta"] == ["value1", "value2", "value3"]

    args = await parser.parse_args(["-c", "value1", "value2"])
    assert args["charlie"] == ["value1", "value2"]

    args = await parser.parse_args(["-c"])
    assert args["charlie"] == []

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a", "value1"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a", "value1", "value2", "value3"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-b"])
