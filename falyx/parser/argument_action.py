# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `ArgumentAction`, an enum used to standardize the behavior of CLI arguments
defined within Falyx command configurations.

Each member of this enum maps to a valid `argparse` like actions or Falyx-specific
behavior used during command argument parsing. This allows declarative configuration
of argument behavior when building CLI commands via `CommandArgumentParser`.

Supports alias coercion for shorthand or config-friendly values, and provides
a consistent interface for downstream argument handling logic.

Exports:
    - ArgumentAction: Enum of allowed actions for command arguments.

Example:
    ArgumentAction("store_true") → ArgumentAction.STORE_TRUE
    ArgumentAction("true")       → ArgumentAction.STORE_TRUE (via alias)
    ArgumentAction("optional")   → ArgumentAction.STORE_BOOL_OPTIONAL
"""
from __future__ import annotations

from enum import Enum


class ArgumentAction(Enum):
    """
    Defines the action to be taken when the argument is encountered.

    This enum mirrors the core behavior of Python's `argparse` actions, with a few
    Falyx-specific extensions. It is used when defining command-line arguments for
    `CommandArgumentParser` or YAML-based argument definitions.

    Members:
        ACTION: Invoke a callable as the argument handler (Falyx extension).
        STORE: Store the provided value (default).
        STORE_TRUE: Store `True` if the flag is present.
        STORE_FALSE: Store `False` if the flag is present.
        STORE_BOOL_OPTIONAL: Accept an optional bool (e.g., `--debug` or `--no-debug`).
        APPEND: Append the value to a list.
        EXTEND: Extend a list with multiple values.
        COUNT: Count the number of occurrences.
        HELP: Display help and exit.
        TLDR: Display brief examples and exit.

    Aliases:
        - "true" → "store_true"
        - "false" → "store_false"
        - "optional" → "store_bool_optional"

    Example:
        ArgumentAction("true") → ArgumentAction.STORE_TRUE
    """

    ACTION = "action"
    STORE = "store"
    STORE_TRUE = "store_true"
    STORE_FALSE = "store_false"
    STORE_BOOL_OPTIONAL = "store_bool_optional"
    APPEND = "append"
    EXTEND = "extend"
    COUNT = "count"
    HELP = "help"
    TLDR = "tldr"

    @classmethod
    def choices(cls) -> list[ArgumentAction]:
        """Return a list of all argument actions."""
        return list(cls)

    @classmethod
    def _get_alias(cls, value: str) -> str:
        aliases = {
            "optional": "store_bool_optional",
            "true": "store_true",
            "false": "store_false",
        }
        return aliases.get(value, value)

    @classmethod
    def _missing_(cls, value: object) -> ArgumentAction:
        if not isinstance(value, str):
            raise ValueError(f"Invalid {cls.__name__}: {value!r}")
        normalized = value.strip().lower()
        alias = cls._get_alias(normalized)
        for member in cls:
            if member.value == alias:
                return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid {cls.__name__}: '{value}'. Must be one of: {valid}")

    def __str__(self) -> str:
        """Return the string representation of the argument action."""
        return self.value
