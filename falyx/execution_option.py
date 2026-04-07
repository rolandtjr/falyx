# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from enum import Enum


class ExecutionOption(Enum):
    SUMMARY = "summary"
    RETRY = "retry"
    CONFIRM = "confirm"

    @classmethod
    def _missing_(cls, value: object) -> ExecutionOption:
        if not isinstance(value, str):
            raise ValueError(f"Invalid {cls.__name__}: {value!r}")
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid {cls.__name__}: '{value}'. Must be one of: {valid}")
