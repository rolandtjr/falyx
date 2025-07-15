import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parser import ArgumentAction, CommandArgumentParser


@pytest.mark.asyncio
async def test_store_bool_optional_true():
    parser = CommandArgumentParser()
    parser.add_argument(
        "--debug",
        action=ArgumentAction.STORE_BOOL_OPTIONAL,
        help="Enable debug mode.",
    )
    args = await parser.parse_args(["--debug"])
    assert args["debug"] is True


@pytest.mark.asyncio
async def test_store_bool_optional_false():
    parser = CommandArgumentParser()
    parser.add_argument(
        "--debug",
        action=ArgumentAction.STORE_BOOL_OPTIONAL,
        help="Enable debug mode.",
    )
    args = await parser.parse_args(["--no-debug"])
    assert args["debug"] is False


@pytest.mark.asyncio
async def test_store_bool_optional_default_none():
    parser = CommandArgumentParser()
    parser.add_argument(
        "--debug",
        action=ArgumentAction.STORE_BOOL_OPTIONAL,
        help="Enable debug mode.",
    )
    args = await parser.parse_args([])
    assert args["debug"] is None


@pytest.mark.asyncio
async def test_store_bool_optional_flag_order():
    parser = CommandArgumentParser()
    parser.add_argument(
        "--dry-run",
        action=ArgumentAction.STORE_BOOL_OPTIONAL,
        help="Run without making changes.",
    )
    args = await parser.parse_args(["--dry-run"])
    assert args["dry_run"] is True
    args = await parser.parse_args(["--no-dry-run"])
    assert args["dry_run"] is False


def test_store_bool_optional_requires_long_flag():
    parser = CommandArgumentParser()
    with pytest.raises(CommandArgumentError):
        parser.add_argument(
            "-d", action=ArgumentAction.STORE_BOOL_OPTIONAL, help="Invalid"
        )


def test_store_bool_optional_disallows_multiple_flags():
    parser = CommandArgumentParser()
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--debug", "-d", action=ArgumentAction.STORE_BOOL_OPTIONAL)


def test_store_bool_optional_duplicate_dest():
    parser = CommandArgumentParser()
    parser.add_argument(
        "--debug",
        action=ArgumentAction.STORE_BOOL_OPTIONAL,
        help="Enable debug mode.",
    )
    with pytest.raises(CommandArgumentError):
        parser.add_argument(
            "--debug",
            action=ArgumentAction.STORE_TRUE,
            help="Conflicting debug option.",
        )
