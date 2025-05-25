import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parsers import ArgumentAction, CommandArgumentParser


@pytest.mark.asyncio
async def test_posix_bundling():
    """Test the bundling of short options in the POSIX style."""
    parser = CommandArgumentParser()
    parser.add_argument(
        "-a", "--alpha", action=ArgumentAction.STORE_FALSE, help="Alpha option"
    )
    parser.add_argument(
        "-b", "--beta", action=ArgumentAction.STORE_TRUE, help="Beta option"
    )
    parser.add_argument(
        "-c", "--charlie", action=ArgumentAction.STORE_TRUE, help="Charlie option"
    )

    # Test valid bundling
    args = await parser.parse_args(["-abc"])
    assert args["alpha"] is False
    assert args["beta"] is True
    assert args["charlie"] is True


@pytest.mark.asyncio
async def test_posix_bundling_last_has_value():
    """Test the bundling of short options in the POSIX style with last option having a value."""
    parser = CommandArgumentParser()
    parser.add_argument(
        "-a", "--alpha", action=ArgumentAction.STORE_TRUE, help="Alpha option"
    )
    parser.add_argument(
        "-b", "--beta", action=ArgumentAction.STORE_TRUE, help="Beta option"
    )
    parser.add_argument(
        "-c", "--charlie", action=ArgumentAction.STORE, help="Charlie option"
    )

    # Test valid bundling with last option having a value
    args = await parser.parse_args(["-abc", "value"])
    assert args["alpha"] is True
    assert args["beta"] is True
    assert args["charlie"] == "value"


@pytest.mark.asyncio
async def test_posix_bundling_invalid():
    """Test the bundling of short options in the POSIX style with invalid cases."""
    parser = CommandArgumentParser()
    parser.add_argument(
        "-a", "--alpha", action=ArgumentAction.STORE_FALSE, help="Alpha option"
    )
    parser.add_argument(
        "-b", "--beta", action=ArgumentAction.STORE_TRUE, help="Beta option"
    )
    parser.add_argument(
        "-c", "--charlie", action=ArgumentAction.STORE, help="Charlie option"
    )

    # Test invalid bundling
    args = await parser.parse_args(["-abc", "value"])
    assert args["alpha"] is False
    assert args["beta"] is True
    assert args["charlie"] == "value"

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a", "value"])
    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-b", "value"])

    args = await parser.parse_args(["-c", "value"])
    assert args["alpha"] is True
    assert args["beta"] is False
    assert args["charlie"] == "value"

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-cab", "value"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a", "-b", "value"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-dbc", "value"])

    with pytest.raises(CommandArgumentError):
        args = await parser.parse_args(["-c"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-abc"])


@pytest.mark.asyncio
async def test_posix_bundling_fuzz():
    """Test the bundling of short options in the POSIX style with fuzzing."""
    parser = CommandArgumentParser()
    parser.add_argument(
        "-a", "--alpha", action=ArgumentAction.STORE_FALSE, help="Alpha option"
    )

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--=value"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--flag="])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a=b"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["---"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a", "-b", "-c"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a", "--", "-b", "-c"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["-a", "--flag", "-b", "-c"])
