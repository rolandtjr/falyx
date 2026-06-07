import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parser import CommandArgumentParser
from falyx.parser.command_argument_parser import _GroupBuilder


def test_group_builder():
    parser = CommandArgumentParser(program="test_program")
    group_builder = _GroupBuilder(parser, group_name="test_group")
    assert group_builder.group_name == "test_group"
    assert "group='test_group'" in str(group_builder)

    group_builder = _GroupBuilder(
        parser,
        mutex_name="test_group",
    )
    assert group_builder.mutex_name == "test_group"
    assert "mutex_group='test_group'" in str(group_builder)

    with pytest.raises(CommandArgumentError):
        _GroupBuilder(parser, group_name="test_group", mutex_name="test_group")

    with pytest.raises(CommandArgumentError):
        _GroupBuilder(parser)

    with pytest.raises(AssertionError):
        builder = _GroupBuilder(parser, group_name="test_group")
        builder.group_name = None
        builder.mutex_name = None
        str(builder)


def test_adding_arguments_to_group():
    parser = CommandArgumentParser(program="test_program")

    group = parser.add_argument_group("test_group")
    assert group.group_name == "test_group"

    group.add_argument("--foo", type=str, help="Foo argument")
    group.add_argument("--bar", type=int, help="Bar argument")

    with pytest.raises(CommandArgumentError):
        parser.add_argument_group("test_group")


def test_adding_arguments_to_mutex_group():
    parser = CommandArgumentParser(program="test_program")

    mutex_group = parser.add_mutually_exclusive_group("test_mutex_group")
    assert mutex_group.mutex_name == "test_mutex_group"

    mutex_group.add_argument("--foo", type=str, help="Foo argument")
    mutex_group.add_argument("--bar", type=int, help="Bar argument")

    with pytest.raises(CommandArgumentError):
        parser.add_mutually_exclusive_group("test_mutex_group")


def test_adding_arguments_to_group_with_invalid_group():
    parser = CommandArgumentParser(program="test_program")

    with pytest.raises(CommandArgumentError):
        parser.add_argument(
            "--foo", type=str, help="Foo argument", group="non_existent_group"
        )

    with pytest.raises(CommandArgumentError):
        parser.add_argument(
            "--bar", type=int, help="Bar argument", mutex_group="non_existent_group"
        )


def test_adding_positional_arguments_to_mutex_group():
    parser = CommandArgumentParser(program="test_program")

    group = parser.add_mutually_exclusive_group("test_group")

    with pytest.raises(CommandArgumentError):
        group.add_argument(
            "positional_arg", type=str, help="This should fail because it's positional"
        )


def test_adding_required_arguments_to_mutex_group():
    parser = CommandArgumentParser(program="test_program")

    group = parser.add_mutually_exclusive_group("test_group")

    with pytest.raises(CommandArgumentError):
        group.add_argument(
            "--foo",
            type=str,
            help="This should fail because it's required",
            required=True,
        )
