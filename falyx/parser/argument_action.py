# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""argument_action.py"""
from __future__ import annotations

from enum import Enum


class ArgumentAction(Enum):
    """Defines the action to be taken when the argument is encountered."""

    ACTION = "action"
    STORE = "store"
    STORE_TRUE = "store_true"
    STORE_FALSE = "store_false"
    APPEND = "append"
    EXTEND = "extend"
    COUNT = "count"
    HELP = "help"

    @classmethod
    def choices(cls) -> list[ArgumentAction]:
        """Return a list of all argument actions."""
        return list(cls)

    def __str__(self) -> str:
        """Return the string representation of the argument action."""
        return self.value
