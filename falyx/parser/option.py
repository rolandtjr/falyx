# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from falyx.parser.option_action import OptionAction


class OptionScope(Enum):
    ROOT = "root"
    NAMESPACE = "namespace"

    @classmethod
    def _missing_(cls, value: object) -> OptionScope:
        if not isinstance(value, str):
            raise ValueError(f"Invalid {cls.__name__}: {value!r}")
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid {cls.__name__}: '{value}'. Must be one of: {valid}")


@dataclass(slots=True)
class Option:
    flags: tuple[str, ...]
    dest: str
    action: OptionAction = OptionAction.STORE
    type: Any = str
    default: Any = None
    choices: list[str] | None = None
    help: str = ""
    suggestions: list[str] | None = None
    scope: OptionScope = OptionScope.NAMESPACE

    def format_for_help(self) -> str:
        """Return a formatted string of the option's flags for help output."""
        return ", ".join(self.flags)
