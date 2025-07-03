import pytest

from falyx.parser import CommandArgumentParser


@pytest.mark.asyncio
async def test_multiple_positional():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("mode", choices=["edit", "view"])

    args = await parser.parse_args(["a", "b", "c", "edit"])
    assert args["files"] == ["a", "b", "c"]
    assert args["mode"] == "edit"


@pytest.mark.asyncio
async def test_multiple_positional_with_default():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("mode", choices=["edit", "view"], default="edit")

    args = await parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]
    assert args["mode"] == "edit"
