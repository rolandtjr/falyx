import pytest

from falyx.action import Action, SelectionAction
from falyx.exceptions import CommandArgumentError
from falyx.parsers import ArgumentAction, CommandArgumentParser


def test_add_argument():
    """Test the add_argument method."""
    parser = CommandArgumentParser()
    action = Action("test_action", lambda: "value")
    parser.add_argument(
        "test", action=ArgumentAction.ACTION, help="Test argument", resolver=action
    )
    with pytest.raises(CommandArgumentError):
        parser.add_argument("test1", action=ArgumentAction.ACTION, help="Test argument")
    with pytest.raises(CommandArgumentError):
        parser.add_argument(
            "test2",
            action=ArgumentAction.ACTION,
            help="Test argument",
            resolver="Not an action",
        )


@pytest.mark.asyncio
async def test_falyx_actions():
    """Test the Falyx actions."""
    parser = CommandArgumentParser()
    action = Action("test_action", lambda: "value")
    parser.add_argument(
        "-a",
        "--alpha",
        action=ArgumentAction.ACTION,
        resolver=action,
        help="Alpha option",
    )

    # Test valid cases
    args = await parser.parse_args(["-a"])
    assert args["alpha"] == "value"


@pytest.mark.asyncio
async def test_action_basic():
    parser = CommandArgumentParser()
    action = Action("hello", lambda: "hi")
    parser.add_argument("--greet", action=ArgumentAction.ACTION, resolver=action)
    args = await parser.parse_args(["--greet"])
    assert args["greet"] == "hi"


@pytest.mark.asyncio
async def test_action_with_nargs():
    parser = CommandArgumentParser()

    def multiply(a, b):
        return int(a) * int(b)

    action = Action("multiply", multiply)
    parser.add_argument("--mul", action=ArgumentAction.ACTION, resolver=action, nargs=2)
    args = await parser.parse_args(["--mul", "3", "4"])
    assert args["mul"] == 12


@pytest.mark.asyncio
async def test_action_with_nargs_positional():
    parser = CommandArgumentParser()

    def multiply(a, b):
        return int(a) * int(b)

    action = Action("multiply", multiply)
    parser.add_argument("mul", action=ArgumentAction.ACTION, resolver=action, nargs=2)
    args = await parser.parse_args(["3", "4"])
    assert args["mul"] == 12

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["3"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args([])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["3", "4", "5"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--mul", "3", "4"])


@pytest.mark.asyncio
async def test_action_with_nargs_positional_int():
    parser = CommandArgumentParser()

    def multiply(a, b):
        return a * b

    action = Action("multiply", multiply)
    parser.add_argument(
        "mul", action=ArgumentAction.ACTION, resolver=action, nargs=2, type=int
    )
    args = await parser.parse_args(["3", "4"])
    assert args["mul"] == 12

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["3"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["abc", "3"])


@pytest.mark.asyncio
async def test_action_with_nargs_type():
    parser = CommandArgumentParser()

    def multiply(a, b):
        return a * b

    action = Action("multiply", multiply)
    parser.add_argument(
        "--mul", action=ArgumentAction.ACTION, resolver=action, nargs=2, type=int
    )
    args = await parser.parse_args(["--mul", "3", "4"])
    assert args["mul"] == 12

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--mul", "abc", "3"])


@pytest.mark.asyncio
async def test_action_with_custom_type():
    parser = CommandArgumentParser()

    def upcase(s):
        return s.upper()

    action = Action("upcase", upcase)
    parser.add_argument("--word", action=ArgumentAction.ACTION, resolver=action, type=str)
    args = await parser.parse_args(["--word", "hello"])
    assert args["word"] == "HELLO"


@pytest.mark.asyncio
async def test_action_with_nargs_star():
    parser = CommandArgumentParser()

    def joiner(*args):
        return "-".join(args)

    action = Action("join", joiner)
    parser.add_argument(
        "--tags", action=ArgumentAction.ACTION, resolver=action, nargs="*"
    )
    args = await parser.parse_args(["--tags", "a", "b", "c"])
    assert args["tags"] == "a-b-c"


@pytest.mark.asyncio
async def test_action_nargs_plus_missing():
    parser = CommandArgumentParser()
    action = Action("noop", lambda *args: args)
    parser.add_argument("--x", action=ArgumentAction.ACTION, resolver=action, nargs="+")
    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--x"])


@pytest.mark.asyncio
async def test_action_with_default():
    parser = CommandArgumentParser()
    action = Action("default", lambda value: value)
    parser.add_argument(
        "--default",
        action=ArgumentAction.ACTION,
        resolver=action,
        default="default_value",
    )
    args = await parser.parse_args([])
    assert args["default"] == "default_value"


@pytest.mark.asyncio
async def test_action_with_default_and_value():
    parser = CommandArgumentParser()
    action = Action("default", lambda value: value)
    parser.add_argument(
        "--default",
        action=ArgumentAction.ACTION,
        resolver=action,
        default="default_value",
    )
    args = await parser.parse_args(["--default", "new_value"])
    assert args["default"] == "new_value"


@pytest.mark.asyncio
async def test_action_with_default_and_value_not():
    parser = CommandArgumentParser()
    action = Action("default", lambda: "default_value")
    parser.add_argument(
        "--default",
        action=ArgumentAction.ACTION,
        resolver=action,
        default="default_value",
    )
    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--default", "new_value"])


@pytest.mark.asyncio
async def test_action_with_default_and_value_positional():
    parser = CommandArgumentParser()
    action = Action("default", lambda: "default_value")
    parser.add_argument("default", action=ArgumentAction.ACTION, resolver=action)

    with pytest.raises(CommandArgumentError):
        await parser.parse_args([])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["be"])


# @pytest.mark.asyncio
# async def test_selection_action():
#     parser = CommandArgumentParser()
#     action = SelectionAction("select", selections=["a", "b", "c"])
#     parser.add_argument("--select", action=ArgumentAction.ACTION, resolver=action)
#     args = await parser.parse_args(["--select"])
