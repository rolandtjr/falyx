import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parsers import ArgumentAction, CommandArgumentParser
from falyx.signals import HelpSignal


async def build_parser_and_parse(args, config):
    cap = CommandArgumentParser()
    config(cap)
    return await cap.parse_args(args)


@pytest.mark.asyncio
async def test_none():
    def config(parser):
        parser.add_argument("--foo", type=str)

    parsed = await build_parser_and_parse(None, config)
    assert parsed["foo"] is None


@pytest.mark.asyncio
async def test_append_multiple_flags():
    def config(parser):
        parser.add_argument("--tag", action=ArgumentAction.APPEND, type=str)

    parsed = await build_parser_and_parse(
        ["--tag", "a", "--tag", "b", "--tag", "c"], config
    )
    assert parsed["tag"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_positional_nargs_plus_and_single():
    def config(parser):
        parser.add_argument("files", nargs="+", type=str)
        parser.add_argument("mode", nargs=1)

    parsed = await build_parser_and_parse(["a", "b", "c", "prod"], config)
    assert parsed["files"] == ["a", "b", "c"]
    assert parsed["mode"] == "prod"


@pytest.mark.asyncio
async def test_type_validation_failure():
    def config(parser):
        parser.add_argument("--count", type=int)

    with pytest.raises(CommandArgumentError):
        await build_parser_and_parse(["--count", "abc"], config)


@pytest.mark.asyncio
async def test_required_field_missing():
    def config(parser):
        parser.add_argument("--env", type=str, required=True)

    with pytest.raises(CommandArgumentError):
        await build_parser_and_parse([], config)


@pytest.mark.asyncio
async def test_choices_enforced():
    def config(parser):
        parser.add_argument("--mode", choices=["dev", "prod"])

    with pytest.raises(CommandArgumentError):
        await build_parser_and_parse(["--mode", "staging"], config)


@pytest.mark.asyncio
async def test_boolean_flags():
    def config(parser):
        parser.add_argument("--debug", action=ArgumentAction.STORE_TRUE)
        parser.add_argument("--no-debug", action=ArgumentAction.STORE_FALSE)

    parsed = await build_parser_and_parse(["--debug", "--no-debug"], config)
    assert parsed["debug"] is True
    assert parsed["no_debug"] is False
    parsed = await build_parser_and_parse([], config)
    assert parsed["debug"] is False
    assert parsed["no_debug"] is True


@pytest.mark.asyncio
async def test_count_action():
    def config(parser):
        parser.add_argument("-v", action=ArgumentAction.COUNT)

    parsed = await build_parser_and_parse(["-v", "-v", "-v"], config)
    assert parsed["v"] == 3


@pytest.mark.asyncio
async def test_nargs_star():
    def config(parser):
        parser.add_argument("args", nargs="*", type=str)

    parsed = await build_parser_and_parse(["one", "two", "three"], config)
    assert parsed["args"] == ["one", "two", "three"]


@pytest.mark.asyncio
async def test_flag_and_positional_mix():
    def config(parser):
        parser.add_argument("--env", type=str)
        parser.add_argument("tasks", nargs="+")

    parsed = await build_parser_and_parse(["--env", "prod", "build", "test"], config)
    assert parsed["env"] == "prod"
    assert parsed["tasks"] == ["build", "test"]


def test_duplicate_dest_fails():
    parser = CommandArgumentParser()
    parser.add_argument("--foo", dest="shared")
    with pytest.raises(CommandArgumentError):
        parser.add_argument("bar", dest="shared")


def test_add_argument_positional_flag_conflict():
    parser = CommandArgumentParser()

    # ✅ Single positional argument should work
    parser.add_argument("faylx")

    # ❌ Multiple positional flags is invalid
    with pytest.raises(CommandArgumentError):
        parser.add_argument("falyx", "test")


def test_add_argument_positional_and_flag_conflict():
    parser = CommandArgumentParser()

    # ❌ Cannot mix positional and optional in one declaration
    with pytest.raises(CommandArgumentError):
        parser.add_argument("faylx", "--falyx")


def test_add_argument_multiple_optional_flags_same_dest():
    parser = CommandArgumentParser()

    # ✅ Valid: multiple flags for same dest
    parser.add_argument("-f", "--falyx")
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ("-f", "--falyx")


def test_add_argument_flag_dest_conflict():
    parser = CommandArgumentParser()

    # First one is fine
    parser.add_argument("falyx")

    # ❌ Cannot reuse dest name with another flag or positional
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--test", dest="falyx")


def test_add_argument_flag_and_positional_conflict_dest_inference():
    parser = CommandArgumentParser()

    # ❌ "--falyx" and "falyx" result in dest conflict
    parser.add_argument("--falyx")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("falyx")


def test_add_argument_multiple_flags_custom_dest():
    parser = CommandArgumentParser()

    # ✅ Multiple flags with explicit dest
    parser.add_argument("-f", "--falyx", "--test", dest="falyx")
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ("-f", "--falyx", "--test")


def test_add_argument_multiple_flags_dest():
    parser = CommandArgumentParser()

    # ✅ Multiple flags with implicit dest first non -flag
    parser.add_argument("-f", "--falyx", "--test")
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ("-f", "--falyx", "--test")


def test_add_argument_single_flag_dest():
    parser = CommandArgumentParser()

    # ✅ Single flag with explicit dest
    parser.add_argument("-f")
    arg = parser._arguments[-1]
    assert arg.dest == "f"
    assert arg.flags == ("-f",)


def test_add_argument_bad_dest():
    parser = CommandArgumentParser()

    # ❌ Invalid dest name
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", dest="1falyx")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", dest="falyx%")


def test_add_argument_bad_flag():
    parser = CommandArgumentParser()

    # ❌ Invalid flag name
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--1falyx")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--!falyx")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("_")

    with pytest.raises(CommandArgumentError):
        parser.add_argument(None)

    with pytest.raises(CommandArgumentError):
        parser.add_argument(0)

    with pytest.raises(CommandArgumentError):
        parser.add_argument("-")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("-asdf")


def test_add_argument_duplicate_flags():
    parser = CommandArgumentParser()

    parser.add_argument("--falyx")

    # ❌ Duplicate flag
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--test", "--falyx")

    # ❌ Duplicate flag
    with pytest.raises(CommandArgumentError):
        parser.add_argument("falyx")


def test_add_argument_no_flags():
    parser = CommandArgumentParser()

    # ❌ No flags provided
    with pytest.raises(CommandArgumentError):
        parser.add_argument()


def test_add_argument_default_value():
    parser = CommandArgumentParser()

    # ✅ Default value provided
    parser.add_argument("--falyx", default="default_value")
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ("--falyx",)
    assert arg.default == "default_value"


def test_add_argument_bad_default():
    parser = CommandArgumentParser()

    # ❌ Invalid default value
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", type=int, default="1falyx")


def test_add_argument_bad_default_list():
    parser = CommandArgumentParser()

    # ❌ Invalid default value
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", type=int, default=["a", 2, 3])


def test_add_argument_bad_action():
    parser = CommandArgumentParser()

    # ❌ Invalid action
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", action="invalid_action")

    # ❌ Invalid action type
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", action=123)


def test_add_argument_default_not_in_choices():
    parser = CommandArgumentParser()

    # ❌ Default value not in choices
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", choices=["a", "b"], default="c")


@pytest.mark.asyncio
async def test_add_argument_choices():
    parser = CommandArgumentParser()

    # ✅ Choices provided
    parser.add_argument("--falyx", choices=["a", "b", "c"])
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ("--falyx",)
    assert arg.choices == ["a", "b", "c"]

    args = await parser.parse_args(["--falyx", "a"])
    assert args["falyx"] == "a"
    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--falyx", "d"])


def test_add_argument_choices_invalid():
    parser = CommandArgumentParser()

    # ❌ Invalid choices
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", choices=["a", "b"], default="c")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--bad", choices=123)

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--bad3", choices={1: "a", 2: "b"})

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--bad4", choices=["a", "b"], type=int)


def test_add_argument_bad_nargs():
    parser = CommandArgumentParser()

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", nargs="invalid")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--foo", nargs="123")

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--foo", nargs=[1, 2])

    with pytest.raises(CommandArgumentError):
        parser.add_argument("--too", action="count", nargs=5)

    with pytest.raises(CommandArgumentError):
        parser.add_argument("falyx", action="store_true", nargs=5)


def test_add_argument_nargs():
    parser = CommandArgumentParser()
    parser.add_argument("--falyx", nargs=2)
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ("--falyx",)
    assert arg.nargs == 2


def test_add_argument_valid_nargs():
    # Valid nargs int, +, * and ?
    parser = CommandArgumentParser()
    parser.add_argument("--falyx", nargs="+")
    arg = parser._arguments[-1]
    assert arg.nargs == "+"

    parser.add_argument("--test", nargs="*")
    arg = parser._arguments[-1]
    assert arg.nargs == "*"

    parser.add_argument("--test2", nargs="?")
    arg = parser._arguments[-1]
    assert arg.nargs == "?"


def test_get_argument():
    parser = CommandArgumentParser()
    parser.add_argument("--falyx", type=str, default="default_value")
    arg = parser.get_argument("falyx")
    assert arg.dest == "falyx"
    assert arg.flags == ("--falyx",)
    assert arg.default == "default_value"


@pytest.mark.asyncio
async def test_parse_args_nargs():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+", type=str)
    parser.add_argument("mode", nargs=1)
    parser.add_argument("--action", action="store_true")

    args = await parser.parse_args(["a", "b", "c", "--action"])
    args = await parser.parse_args(["--action", "a", "b", "c"])

    assert args["files"] == ["a", "b"]
    assert args["mode"] == "c"


@pytest.mark.asyncio
async def test_parse_args_nargs_plus():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+", type=str)

    args = await parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    args = await parser.parse_args(["a"])
    assert args["files"] == ["a"]


@pytest.mark.asyncio
async def test_parse_args_flagged_nargs_plus():
    parser = CommandArgumentParser()
    parser.add_argument("--files", nargs="+", type=str)

    args = await parser.parse_args(["--files", "a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    args = await parser.parse_args(["--files", "a"])
    print(args)
    assert args["files"] == ["a"]

    args = await parser.parse_args([])
    assert args["files"] == []


@pytest.mark.asyncio
async def test_parse_args_numbered_nargs():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs=2, type=str)

    args = await parser.parse_args(["a", "b"])
    assert args["files"] == ["a", "b"]

    with pytest.raises(CommandArgumentError):
        args = await parser.parse_args(["a"])
        print(args)


def test_parse_args_nargs_zero():
    parser = CommandArgumentParser()
    with pytest.raises(CommandArgumentError):
        parser.add_argument("files", nargs=0, type=str)


@pytest.mark.asyncio
async def test_parse_args_nargs_more_than_expected():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs=2, type=str)

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["a", "b", "c", "d"])


@pytest.mark.asyncio
async def test_parse_args_nargs_one_or_none():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="?", type=str)

    args = await parser.parse_args(["a"])
    assert args["files"] == "a"

    args = await parser.parse_args([])
    assert args["files"] is None


@pytest.mark.asyncio
async def test_parse_args_nargs_positional():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="*", type=str)

    args = await parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    args = await parser.parse_args([])
    assert args["files"] == []


@pytest.mark.asyncio
async def test_parse_args_nargs_positional_plus():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+", type=str)

    args = await parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    with pytest.raises(CommandArgumentError):
        args = await parser.parse_args([])


@pytest.mark.asyncio
async def test_parse_args_nargs_multiple_positional():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+", type=str)
    parser.add_argument("mode", nargs=1)
    parser.add_argument("action", nargs="?")
    parser.add_argument("target", nargs="*")
    parser.add_argument("extra", nargs="+")

    args = await parser.parse_args(["a", "b", "c", "d", "e"])
    assert args["files"] == ["a", "b", "c"]
    assert args["mode"] == "d"
    assert args["action"] == []
    assert args["target"] == []
    assert args["extra"] == ["e"]

    with pytest.raises(CommandArgumentError):
        await parser.parse_args([])


@pytest.mark.asyncio
async def test_parse_args_nargs_none():
    parser = CommandArgumentParser()
    parser.add_argument("numbers", type=int)
    parser.add_argument("mode")

    await parser.parse_args(["1", "2"])


@pytest.mark.asyncio
async def test_parse_args_nargs_invalid_positional_arguments():
    parser = CommandArgumentParser()
    parser.add_argument("numbers", nargs="*", type=int)
    parser.add_argument("mode", nargs=1)

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["1", "2", "c", "d"])


@pytest.mark.asyncio
async def test_parse_args_append():
    parser = CommandArgumentParser()
    parser.add_argument("--numbers", action=ArgumentAction.APPEND, type=int)

    args = await parser.parse_args(["--numbers", "1", "--numbers", "2", "--numbers", "3"])
    assert args["numbers"] == [1, 2, 3]

    args = await parser.parse_args(["--numbers", "1"])
    assert args["numbers"] == [1]

    args = await parser.parse_args([])
    assert args["numbers"] == []


@pytest.mark.asyncio
async def test_parse_args_nargs_int_append():
    parser = CommandArgumentParser()
    parser.add_argument("--numbers", action=ArgumentAction.APPEND, type=int, nargs=1)

    args = await parser.parse_args(["--numbers", "1", "--numbers", "2", "--numbers", "3"])
    assert args["numbers"] == [[1], [2], [3]]

    args = await parser.parse_args(["--numbers", "1"])
    assert args["numbers"] == [[1]]

    args = await parser.parse_args([])
    assert args["numbers"] == []


@pytest.mark.asyncio
async def test_parse_args_nargs_append():
    parser = CommandArgumentParser()
    parser.add_argument("numbers", action=ArgumentAction.APPEND, type=int, nargs="*")
    parser.add_argument("--mode")

    args = await parser.parse_args(["1"])
    assert args["numbers"] == [[1]]

    args = await parser.parse_args(["1", "2", "3", "--mode", "numbers", "4", "5"])
    assert args["numbers"] == [[1, 2, 3], [4, 5]]
    assert args["mode"] == "numbers"

    args = await parser.parse_args(["1", "2", "3"])
    assert args["numbers"] == [[1, 2, 3]]

    args = await parser.parse_args([])
    assert args["numbers"] == []


@pytest.mark.asyncio
async def test_parse_args_int_optional_append():
    parser = CommandArgumentParser()
    parser.add_argument("numbers", action=ArgumentAction.APPEND, type=int)

    args = await parser.parse_args(["1"])
    assert args["numbers"] == [1]


@pytest.mark.asyncio
async def test_parse_args_int_optional_append_multiple_values():
    parser = CommandArgumentParser()
    parser.add_argument("numbers", action=ArgumentAction.APPEND, type=int)

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["1", "2"])


@pytest.mark.asyncio
async def test_parse_args_nargs_int_positional_append():
    parser = CommandArgumentParser()
    parser.add_argument("numbers", action=ArgumentAction.APPEND, type=int, nargs=1)

    args = await parser.parse_args(["1"])
    assert args["numbers"] == [[1]]

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["1", "2", "3"])

    parser2 = CommandArgumentParser()
    parser2.add_argument("numbers", action=ArgumentAction.APPEND, type=int, nargs=2)

    args = await parser2.parse_args(["1", "2"])
    assert args["numbers"] == [[1, 2]]

    with pytest.raises(CommandArgumentError):
        await parser2.parse_args(["1", "2", "3"])


@pytest.mark.asyncio
async def test_parse_args_append_flagged_invalid_type():
    parser = CommandArgumentParser()
    parser.add_argument("--numbers", action=ArgumentAction.APPEND, type=int)

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--numbers", "a"])


@pytest.mark.asyncio
async def test_append_groups_nargs():
    cap = CommandArgumentParser()
    cap.add_argument("--item", action=ArgumentAction.APPEND, type=str, nargs=2)

    parsed = await cap.parse_args(["--item", "a", "b", "--item", "c", "d"])
    assert parsed["item"] == [["a", "b"], ["c", "d"]]

    with pytest.raises(CommandArgumentError):
        await cap.parse_args(["--item", "a", "b", "--item", "c"])


@pytest.mark.asyncio
async def test_extend_flattened():
    cap = CommandArgumentParser()
    cap.add_argument("--value", action=ArgumentAction.EXTEND, type=str)

    parsed = await cap.parse_args(["--value", "x", "--value", "y"])
    assert parsed["value"] == ["x", "y"]


@pytest.mark.asyncio
async def test_parse_args_split_order():
    cap = CommandArgumentParser()
    cap.add_argument("a")
    cap.add_argument("--x")
    cap.add_argument("b", nargs="*")
    args, kwargs = await cap.parse_args_split(["1", "--x", "100", "2"])
    assert args == ("1", ["2"])
    assert kwargs == {"x": "100"}


@pytest.mark.asyncio
async def test_help_signal_triggers():
    parser = CommandArgumentParser()
    parser.add_argument("--foo")
    with pytest.raises(HelpSignal):
        await parser.parse_args(["--help"])


@pytest.mark.asyncio
async def test_empty_parser_defaults():
    parser = CommandArgumentParser()
    with pytest.raises(HelpSignal):
        await parser.parse_args(["--help"])


@pytest.mark.asyncio
async def test_extend_basic():
    parser = CommandArgumentParser()
    parser.add_argument("--tag", action=ArgumentAction.EXTEND, type=str)

    args = await parser.parse_args(["--tag", "a", "--tag", "b", "--tag", "c"])
    assert args["tag"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_extend_nargs_2():
    parser = CommandArgumentParser()
    parser.add_argument("--pair", action=ArgumentAction.EXTEND, type=str, nargs=2)

    args = await parser.parse_args(["--pair", "a", "b", "--pair", "c", "d"])
    assert args["pair"] == ["a", "b", "c", "d"]


@pytest.mark.asyncio
async def test_extend_nargs_star():
    parser = CommandArgumentParser()
    parser.add_argument("--files", action=ArgumentAction.EXTEND, type=str, nargs="*")

    args = await parser.parse_args(["--files", "x", "y", "z"])
    assert args["files"] == ["x", "y", "z"]

    args = await parser.parse_args(["--files"])
    assert args["files"] == []


@pytest.mark.asyncio
async def test_extend_nargs_plus():
    parser = CommandArgumentParser()
    parser.add_argument("--inputs", action=ArgumentAction.EXTEND, type=int, nargs="+")

    args = await parser.parse_args(["--inputs", "1", "2", "3", "--inputs", "4"])
    assert args["inputs"] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_extend_invalid_type():
    parser = CommandArgumentParser()
    parser.add_argument("--nums", action=ArgumentAction.EXTEND, type=int)

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--nums", "a"])


@pytest.mark.asyncio
async def test_greedy_invalid_type():
    parser = CommandArgumentParser()
    parser.add_argument("--nums", nargs="*", type=int)
    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--nums", "a"])


@pytest.mark.asyncio
async def test_append_vs_extend_behavior():
    parser = CommandArgumentParser()
    parser.add_argument("--x", action=ArgumentAction.APPEND, nargs=2)
    parser.add_argument("--y", action=ArgumentAction.EXTEND, nargs=2)

    args = await parser.parse_args(
        ["--x", "a", "b", "--x", "c", "d", "--y", "1", "2", "--y", "3", "4"]
    )
    assert args["x"] == [["a", "b"], ["c", "d"]]
    assert args["y"] == ["1", "2", "3", "4"]


@pytest.mark.asyncio
async def test_append_vs_extend_behavior_error():
    parser = CommandArgumentParser()
    parser.add_argument("--x", action=ArgumentAction.APPEND, nargs=2)
    parser.add_argument("--y", action=ArgumentAction.EXTEND, nargs=2)

    # This should raise an error because the last argument is not a valid pair
    with pytest.raises(CommandArgumentError):
        await parser.parse_args(
            ["--x", "a", "b", "--x", "c", "d", "--y", "1", "2", "--y", "3"]
        )

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(
            ["--x", "a", "b", "--x", "c", "--y", "1", "--y", "3", "4"]
        )


@pytest.mark.asyncio
async def test_extend_positional():
    parser = CommandArgumentParser()
    parser.add_argument("files", action=ArgumentAction.EXTEND, type=str, nargs="*")

    args = await parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    args = await parser.parse_args([])
    assert args["files"] == []


@pytest.mark.asyncio
async def test_extend_positional_nargs():
    parser = CommandArgumentParser()
    parser.add_argument("files", action=ArgumentAction.EXTEND, type=str, nargs="+")

    args = await parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    with pytest.raises(CommandArgumentError):
        await parser.parse_args([])


def test_command_argument_parser_equality():
    parser1 = CommandArgumentParser()
    parser2 = CommandArgumentParser()

    parser1.add_argument("--foo", type=str)
    parser2.add_argument("--foo", type=str)

    assert parser1 == parser2

    parser1.add_argument("--bar", type=int)
    assert parser1 != parser2

    parser2.add_argument("--bar", type=int)
    assert parser1 == parser2

    assert parser1 != "not a parser"
    assert parser1 is not None
    assert parser1 != object()

    assert parser1.to_definition_list() == parser2.to_definition_list()
    assert hash(parser1) == hash(parser2)


@pytest.mark.asyncio
async def test_render_help():
    parser = CommandArgumentParser()
    parser.add_argument("--foo", type=str, help="Foo help")
    parser.add_argument("--bar", action=ArgumentAction.APPEND, type=str, help="Bar help")

    assert parser.render_help() is None
