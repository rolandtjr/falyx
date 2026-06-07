# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from enum import Enum


class OptionAction(Enum):
    STORE = "store"
    STORE_TRUE = "store_true"
    STORE_FALSE = "store_false"
    STORE_BOOL_OPTIONAL = "store_bool_optional"
    COUNT = "count"
    HELP = "help"
    TLDR = "tldr"

    @classmethod
    def choices(cls) -> list[OptionAction]:
        """Return a list of all option actions."""
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
    def _missing_(cls, value: object) -> OptionAction:
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
        """Return the string representation of the option action."""
        return self.value
