import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parsers import CommandArgumentParser


def test_str():
    """Test the string representation of CommandArgumentParser."""
    parser = CommandArgumentParser()
    assert (
        str(parser)
        == "CommandArgumentParser(args=1, flags=2, keywords=2, positional=0, required=0)"
    )

    parser.add_argument("test", action="store", help="Test argument")
    assert (
        str(parser)
        == "CommandArgumentParser(args=2, flags=3, keywords=2, positional=1, required=1)"
    )

    parser.add_argument("-o", "--optional", action="store", help="Optional argument")
    assert (
        str(parser)
        == "CommandArgumentParser(args=3, flags=5, keywords=4, positional=1, required=1)"
    )

    parser.add_argument("--flag", action="store", help="Flag argument", required=True)
    assert (
        str(parser)
        == "CommandArgumentParser(args=4, flags=6, keywords=5, positional=1, required=2)"
    )
    assert (
        repr(parser)
        == "CommandArgumentParser(args=4, flags=6, keywords=5, positional=1, required=2)"
    )


@pytest.mark.asyncio
async def test_positional_text_with_choices():
    parser = CommandArgumentParser()
    parser.add_argument("path", choices=["a", "b"])
    args = await parser.parse_args(["a"])
    assert args["path"] == "a"

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["c"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args([])
