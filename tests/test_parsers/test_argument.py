import pytest

from falyx.parser import Argument, ArgumentAction


def test_positional_text_with_choices():
    arg = Argument(flags=("path",), dest="path", positional=True, choices=["a", "b"])
    assert arg.get_positional_text() == "{a,b}"


def test_positional_text_without_choices():
    arg = Argument(flags=("path",), dest="path", positional=True)
    assert arg.get_positional_text() == "path"


@pytest.mark.parametrize(
    "nargs,expected",
    [
        (None, "VALUE"),
        (1, "VALUE"),
        ("?", "[VALUE]"),
        ("*", "[VALUE ...]"),
        ("+", "VALUE [VALUE ...]"),
    ],
)
def test_choice_text_store_action_variants(nargs, expected):
    arg = Argument(
        flags=("--value",), dest="value", action=ArgumentAction.STORE, nargs=nargs
    )
    assert arg.get_choice_text() == expected


@pytest.mark.parametrize(
    "nargs,expected",
    [
        (None, "value"),
        (1, "value"),
        ("?", "[value]"),
        ("*", "[value ...]"),
        ("+", "value [value ...]"),
    ],
)
def test_choice_text_store_action_variants_positional(nargs, expected):
    arg = Argument(
        flags=("value",),
        dest="value",
        action=ArgumentAction.STORE,
        nargs=nargs,
        positional=True,
    )
    assert arg.get_choice_text() == expected


def test_choice_text_with_choices():
    arg = Argument(flags=("--mode",), dest="mode", choices=["dev", "prod"])
    assert arg.get_choice_text() == "{dev,prod}"


def test_choice_text_append_and_extend():
    for action in [ArgumentAction.APPEND, ArgumentAction.EXTEND]:
        arg = Argument(flags=("--tag",), dest="tag", action=action)
        assert arg.get_choice_text() == "TAG"


def test_equality():
    a1 = Argument(flags=("--f",), dest="f")
    a2 = Argument(flags=("--f",), dest="f")
    a3 = Argument(flags=("-x",), dest="x")

    assert a1 == a2
    assert a1 != a3
    assert hash(a1) == hash(a2)


def test_inequality_with_non_argument():
    arg = Argument(flags=("--f",), dest="f")
    assert arg != "not an argument"


def test_argument_equality():
    arg = Argument("--foo", dest="foo", type=str, default="default_value")
    arg2 = Argument("--foo", dest="foo", type=str, default="default_value")
    arg3 = Argument("--bar", dest="bar", type=int, default=42)
    arg4 = Argument("--foo", dest="foo", type=str, default="foobar")
    assert arg == arg2
    assert arg != arg3
    assert arg != arg4
    assert arg != "not an argument"
    assert arg is not None
    assert arg != object()


def test_argument_required():
    arg = Argument("--foo", dest="foo", required=True)
    assert arg.required is True

    arg2 = Argument("--bar", dest="bar", required=False)
    assert arg2.required is False
