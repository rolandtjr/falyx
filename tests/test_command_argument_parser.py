import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parsers import ArgumentAction, CommandArgumentParser
from falyx.signals import HelpSignal


def build_parser_and_parse(args, config):
    cap = CommandArgumentParser()
    config(cap)
    return cap.parse_args(args)


def test_none():
    def config(parser):
        parser.add_argument("--foo", type=str)

    parsed = build_parser_and_parse(None, config)
    assert parsed["foo"] is None


def test_append_multiple_flags():
    def config(parser):
        parser.add_argument("--tag", action=ArgumentAction.APPEND, type=str)

    parsed = build_parser_and_parse(["--tag", "a", "--tag", "b", "--tag", "c"], config)
    assert parsed["tag"] == ["a", "b", "c"]


def test_positional_nargs_plus_and_single():
    def config(parser):
        parser.add_argument("files", nargs="+", type=str)
        parser.add_argument("mode", nargs=1)

    parsed = build_parser_and_parse(["a", "b", "c", "prod"], config)
    assert parsed["files"] == ["a", "b", "c"]
    assert parsed["mode"] == "prod"


def test_type_validation_failure():
    def config(parser):
        parser.add_argument("--count", type=int)

    with pytest.raises(CommandArgumentError):
        build_parser_and_parse(["--count", "abc"], config)


def test_required_field_missing():
    def config(parser):
        parser.add_argument("--env", type=str, required=True)

    with pytest.raises(CommandArgumentError):
        build_parser_and_parse([], config)


def test_choices_enforced():
    def config(parser):
        parser.add_argument("--mode", choices=["dev", "prod"])

    with pytest.raises(CommandArgumentError):
        build_parser_and_parse(["--mode", "staging"], config)


def test_boolean_flags():
    def config(parser):
        parser.add_argument("--debug", action=ArgumentAction.STORE_TRUE)
        parser.add_argument("--no-debug", action=ArgumentAction.STORE_FALSE)

    parsed = build_parser_and_parse(["--debug", "--no-debug"], config)
    assert parsed["debug"] is True
    assert parsed["no_debug"] is False
    parsed = build_parser_and_parse([], config)
    print(parsed)
    assert parsed["debug"] is False
    assert parsed["no_debug"] is True


def test_count_action():
    def config(parser):
        parser.add_argument("-v", action=ArgumentAction.COUNT)

    parsed = build_parser_and_parse(["-v", "-v", "-v"], config)
    assert parsed["v"] == 3


def test_nargs_star():
    def config(parser):
        parser.add_argument("args", nargs="*", type=str)

    parsed = build_parser_and_parse(["one", "two", "three"], config)
    assert parsed["args"] == ["one", "two", "three"]


def test_flag_and_positional_mix():
    def config(parser):
        parser.add_argument("--env", type=str)
        parser.add_argument("tasks", nargs="+")

    parsed = build_parser_and_parse(["--env", "prod", "build", "test"], config)
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
    assert arg.flags == ["-f", "--falyx"]


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
    assert arg.flags == ["-f", "--falyx", "--test"]


def test_add_argument_multiple_flags_dest():
    parser = CommandArgumentParser()

    # ✅ Multiple flags with implicit dest first non -flag
    parser.add_argument("-f", "--falyx", "--test")
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ["-f", "--falyx", "--test"]


def test_add_argument_single_flag_dest():
    parser = CommandArgumentParser()

    # ✅ Single flag with explicit dest
    parser.add_argument("-f")
    arg = parser._arguments[-1]
    assert arg.dest == "f"
    assert arg.flags == ["-f"]


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
    assert arg.flags == ["--falyx"]
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


def test_add_argument_choices():
    parser = CommandArgumentParser()

    # ✅ Choices provided
    parser.add_argument("--falyx", choices=["a", "b", "c"])
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ["--falyx"]
    assert arg.choices == ["a", "b", "c"]

    args = parser.parse_args(["--falyx", "a"])
    assert args["falyx"] == "a"
    with pytest.raises(CommandArgumentError):
        parser.parse_args(["--falyx", "d"])


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

    # ❌ Invalid nargs value
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", nargs="invalid")

    # ❌ Invalid nargs type
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", nargs=123)

    # ❌ Invalid nargs type
    with pytest.raises(CommandArgumentError):
        parser.add_argument("--falyx", nargs=None)


def test_add_argument_nargs():
    parser = CommandArgumentParser()
    # ✅ Valid nargs value
    parser.add_argument("--falyx", nargs=2)
    arg = parser._arguments[-1]
    assert arg.dest == "falyx"
    assert arg.flags == ["--falyx"]
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
    assert arg.flags == ["--falyx"]
    assert arg.default == "default_value"


def test_parse_args_nargs():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+", type=str)
    parser.add_argument("mode", nargs=1)

    args = parser.parse_args(["a", "b", "c"])

    assert args["files"] == ["a", "b"]
    assert args["mode"] == "c"


def test_parse_args_nargs_plus():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+", type=str)

    args = parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    args = parser.parse_args(["a"])
    assert args["files"] == ["a"]


def test_parse_args_flagged_nargs_plus():
    parser = CommandArgumentParser()
    parser.add_argument("--files", nargs="+", type=str)

    args = parser.parse_args(["--files", "a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    args = parser.parse_args(["--files", "a"])
    print(args)
    assert args["files"] == ["a"]

    args = parser.parse_args([])
    assert args["files"] == []


def test_parse_args_numbered_nargs():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs=2, type=str)

    args = parser.parse_args(["a", "b"])
    assert args["files"] == ["a", "b"]

    with pytest.raises(CommandArgumentError):
        args = parser.parse_args(["a"])
        print(args)


def test_parse_args_nargs_zero():
    parser = CommandArgumentParser()
    with pytest.raises(CommandArgumentError):
        parser.add_argument("files", nargs=0, type=str)


def test_parse_args_nargs_more_than_expected():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs=2, type=str)

    with pytest.raises(CommandArgumentError):
        parser.parse_args(["a", "b", "c", "d"])


def test_parse_args_nargs_one_or_none():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="?", type=str)

    args = parser.parse_args(["a"])
    assert args["files"] == "a"

    args = parser.parse_args([])
    assert args["files"] is None


def test_parse_args_nargs_positional():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="*", type=str)

    args = parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    args = parser.parse_args([])
    assert args["files"] == []


def test_parse_args_nargs_positional_plus():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+", type=str)

    args = parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    with pytest.raises(CommandArgumentError):
        args = parser.parse_args([])


def test_parse_args_nargs_multiple_positional():
    parser = CommandArgumentParser()
    parser.add_argument("files", nargs="+", type=str)
    parser.add_argument("mode", nargs=1)
    parser.add_argument("action", nargs="?")
    parser.add_argument("target", nargs="*")
    parser.add_argument("extra", nargs="+")

    args = parser.parse_args(["a", "b", "c", "d", "e"])
    assert args["files"] == ["a", "b", "c"]
    assert args["mode"] == "d"
    assert args["action"] == []
    assert args["target"] == []
    assert args["extra"] == ["e"]

    with pytest.raises(CommandArgumentError):
        parser.parse_args([])


def test_parse_args_nargs_invalid_positional_arguments():
    parser = CommandArgumentParser()
    parser.add_argument("numbers", nargs="*", type=int)
    parser.add_argument("mode", nargs=1)

    with pytest.raises(CommandArgumentError):
        parser.parse_args(["1", "2", "c", "d"])


def test_parse_args_append():
    parser = CommandArgumentParser()
    parser.add_argument("--numbers", action=ArgumentAction.APPEND, type=int)

    args = parser.parse_args(["--numbers", "1", "--numbers", "2", "--numbers", "3"])
    assert args["numbers"] == [1, 2, 3]

    args = parser.parse_args(["--numbers", "1"])
    assert args["numbers"] == [1]

    args = parser.parse_args([])
    assert args["numbers"] == []


def test_parse_args_nargs_append():
    parser = CommandArgumentParser()
    parser.add_argument("numbers", action=ArgumentAction.APPEND, type=int, nargs="*")
    parser.add_argument("--mode")

    args = parser.parse_args(["1", "2", "3", "--mode", "numbers", "4", "5"])
    assert args["numbers"] == [[1, 2, 3], [4, 5]]

    args = parser.parse_args(["1"])
    assert args["numbers"] == [[1]]

    args = parser.parse_args([])
    assert args["numbers"] == []


def test_parse_args_append_flagged_invalid_type():
    parser = CommandArgumentParser()
    parser.add_argument("--numbers", action=ArgumentAction.APPEND, type=int)

    with pytest.raises(CommandArgumentError):
        parser.parse_args(["--numbers", "a"])


def test_append_groups_nargs():
    cap = CommandArgumentParser()
    cap.add_argument("--item", action=ArgumentAction.APPEND, type=str, nargs=2)

    parsed = cap.parse_args(["--item", "a", "b", "--item", "c", "d"])
    assert parsed["item"] == [["a", "b"], ["c", "d"]]


def test_extend_flattened():
    cap = CommandArgumentParser()
    cap.add_argument("--value", action=ArgumentAction.EXTEND, type=str)

    parsed = cap.parse_args(["--value", "x", "--value", "y"])
    assert parsed["value"] == ["x", "y"]


def test_parse_args_split_order():
    cap = CommandArgumentParser()
    cap.add_argument("a")
    cap.add_argument("--x")
    cap.add_argument("b", nargs="*")
    args, kwargs = cap.parse_args_split(["1", "--x", "100", "2"])
    assert args == ("1", ["2"])
    assert kwargs == {"x": "100"}


def test_help_signal_triggers():
    parser = CommandArgumentParser()
    parser.add_argument("--foo")
    with pytest.raises(HelpSignal):
        parser.parse_args(["--help"])


def test_empty_parser_defaults():
    parser = CommandArgumentParser()
    with pytest.raises(HelpSignal):
        parser.parse_args(["--help"])


def test_extend_basic():
    parser = CommandArgumentParser()
    parser.add_argument("--tag", action=ArgumentAction.EXTEND, type=str)

    args = parser.parse_args(["--tag", "a", "--tag", "b", "--tag", "c"])
    assert args["tag"] == ["a", "b", "c"]


def test_extend_nargs_2():
    parser = CommandArgumentParser()
    parser.add_argument("--pair", action=ArgumentAction.EXTEND, type=str, nargs=2)

    args = parser.parse_args(["--pair", "a", "b", "--pair", "c", "d"])
    assert args["pair"] == ["a", "b", "c", "d"]


def test_extend_nargs_star():
    parser = CommandArgumentParser()
    parser.add_argument("--files", action=ArgumentAction.EXTEND, type=str, nargs="*")

    args = parser.parse_args(["--files", "x", "y", "z"])
    assert args["files"] == ["x", "y", "z"]

    args = parser.parse_args(["--files"])
    assert args["files"] == []


def test_extend_nargs_plus():
    parser = CommandArgumentParser()
    parser.add_argument("--inputs", action=ArgumentAction.EXTEND, type=int, nargs="+")

    args = parser.parse_args(["--inputs", "1", "2", "3", "--inputs", "4"])
    assert args["inputs"] == [1, 2, 3, 4]


def test_extend_invalid_type():
    parser = CommandArgumentParser()
    parser.add_argument("--nums", action=ArgumentAction.EXTEND, type=int)

    with pytest.raises(CommandArgumentError):
        parser.parse_args(["--nums", "a"])


def test_greedy_invalid_type():
    parser = CommandArgumentParser()
    parser.add_argument("--nums", nargs="*", type=int)
    with pytest.raises(CommandArgumentError):
        parser.parse_args(["--nums", "a"])


def test_append_vs_extend_behavior():
    parser = CommandArgumentParser()
    parser.add_argument("--x", action=ArgumentAction.APPEND, nargs=2)
    parser.add_argument("--y", action=ArgumentAction.EXTEND, nargs=2)

    args = parser.parse_args(
        ["--x", "a", "b", "--x", "c", "d", "--y", "1", "2", "--y", "3", "4"]
    )
    assert args["x"] == [["a", "b"], ["c", "d"]]
    assert args["y"] == ["1", "2", "3", "4"]


def test_append_vs_extend_behavior_error():
    parser = CommandArgumentParser()
    parser.add_argument("--x", action=ArgumentAction.APPEND, nargs=2)
    parser.add_argument("--y", action=ArgumentAction.EXTEND, nargs=2)

    # This should raise an error because the last argument is not a valid pair
    with pytest.raises(CommandArgumentError):
        parser.parse_args(["--x", "a", "b", "--x", "c", "d", "--y", "1", "2", "--y", "3"])

    with pytest.raises(CommandArgumentError):
        parser.parse_args(["--x", "a", "b", "--x", "c", "--y", "1", "--y", "3", "4"])


def test_extend_positional():
    parser = CommandArgumentParser()
    parser.add_argument("files", action=ArgumentAction.EXTEND, type=str, nargs="*")

    args = parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    args = parser.parse_args([])
    assert args["files"] == []


def test_extend_positional_nargs():
    parser = CommandArgumentParser()
    parser.add_argument("files", action=ArgumentAction.EXTEND, type=str, nargs="+")

    args = parser.parse_args(["a", "b", "c"])
    assert args["files"] == ["a", "b", "c"]

    with pytest.raises(CommandArgumentError):
        parser.parse_args([])
