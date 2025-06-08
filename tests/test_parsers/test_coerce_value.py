from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

import pytest

from falyx.parser.utils import coerce_value


# --- Tests ---
@pytest.mark.parametrize(
    "value, target_type, expected",
    [
        ("42", int, 42),
        ("3.14", float, 3.14),
        ("True", bool, True),
        ("hello", str, "hello"),
        ("", str, ""),
        ("False", bool, False),
    ],
)
def test_coerce_value_basic(value, target_type, expected):
    assert coerce_value(value, target_type) == expected


@pytest.mark.parametrize(
    "value, target_type, expected",
    [
        ("42", int | float, 42),
        ("3.14", int | float, 3.14),
        ("hello", str | int, "hello"),
        ("1", bool | str, True),
    ],
)
def test_coerce_value_union_success(value, target_type, expected):
    assert coerce_value(value, target_type) == expected


def test_coerce_value_union_failure():
    with pytest.raises(ValueError) as excinfo:
        coerce_value("abc", int | float)
    assert "could not be coerced" in str(excinfo.value)


def test_coerce_value_typing_union_equivalent():
    from typing import Union

    assert coerce_value("123", Union[int, str]) == 123
    assert coerce_value("abc", Union[int, str]) == "abc"


def test_coerce_value_edge_cases():
    # int -> raises
    with pytest.raises(ValueError):
        coerce_value("not-an-int", int | float)

    # empty string with str fallback
    assert coerce_value("", int | str) == ""

    # bool conversion
    assert coerce_value("False", bool | str) is False


def test_coerce_value_enum():
    class Color(Enum):
        RED = "red"
        GREEN = "green"
        BLUE = "blue"

    assert coerce_value("red", Color) == Color.RED
    assert coerce_value("green", Color) == Color.GREEN
    assert coerce_value("blue", Color) == Color.BLUE

    with pytest.raises(ValueError):
        coerce_value("yellow", Color)  # Not a valid enum value


def test_coerce_value_int_enum():
    class Status(Enum):
        SUCCESS = 0
        FAILURE = 1
        PENDING = 2

    assert coerce_value("0", Status) == Status.SUCCESS
    assert coerce_value(1, Status) == Status.FAILURE
    assert coerce_value("PENDING", Status) == Status.PENDING
    assert coerce_value(Status.SUCCESS, Status) == Status.SUCCESS

    with pytest.raises(ValueError):
        coerce_value("3", Status)

    with pytest.raises(ValueError):
        coerce_value(3, Status)


class Mode(Enum):
    DEV = "dev"
    PROD = "prod"


def test_literal_coercion():
    assert coerce_value("dev", Literal["dev", "prod"]) == "dev"
    try:
        coerce_value("staging", Literal["dev", "prod"])
        assert False
    except ValueError:
        assert True


def test_enum_coercion():
    assert coerce_value("dev", Mode) == Mode.DEV
    assert coerce_value("DEV", Mode) == Mode.DEV
    try:
        coerce_value("staging", Mode)
        assert False
    except ValueError:
        assert True


def test_union_coercion():
    assert coerce_value("123", int | str) == 123
    assert coerce_value("abc", int | str) == "abc"
    assert coerce_value("False", bool | str) is False


def test_path_coercion():
    result = coerce_value("/tmp/test.txt", Path)
    assert isinstance(result, Path)
    assert str(result) == "/tmp/test.txt"


def test_datetime_coercion():
    result = coerce_value("2023-10-01T13:00:00", datetime)
    assert isinstance(result, datetime)
    assert result.year == 2023 and result.month == 10

    with pytest.raises(ValueError):
        coerce_value("not-a-date", datetime)


def test_bool_coercion():
    assert coerce_value("true", bool) is True
    assert coerce_value("False", bool) is False
    assert coerce_value("0", bool) is False
    assert coerce_value("", bool) is False
    assert coerce_value("1", bool) is True
    assert coerce_value("yes", bool) is True
    assert coerce_value("no", bool) is False
    assert coerce_value("on", bool) is True
    assert coerce_value("off", bool) is False
    assert coerce_value(True, bool) is True
    assert coerce_value(False, bool) is False
