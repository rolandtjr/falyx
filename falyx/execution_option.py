# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Execution option enums for the Falyx command runtime.

This module defines `ExecutionOption`, the enum used to represent optional
execution-scoped behaviors that a command may choose to expose through its
argument parser.

Execution options are distinct from normal command inputs. They control runtime
behavior around command execution rather than the business-logic arguments
passed to the underlying action. Typical examples include summary output,
retry configuration, and confirmation handling.

`ExecutionOption` is used by Falyx components such as `Command` and
`CommandArgumentParser` to declaratively enable execution-level flags and to
normalize user- or config-provided option names into a validated enum value.

The enum also implements custom missing-value handling so string inputs can be
resolved case-insensitively with helpful error messages.
"""
from __future__ import annotations

from enum import Enum


class ExecutionOption(Enum):
    """Enumerates optional execution-scoped behaviors supported by Falyx.

    `ExecutionOption` identifies runtime features that can be enabled on a
    command independently of its normal argument schema. When present, these
    options typically cause `CommandArgumentParser` to expose additional flags
    that affect how the command is executed rather than what the command does.

    Supported options:
        SUMMARY: Enable summary-related execution flags and reporting behavior.
        RETRY: Enable retry-related execution flags such as retry count, delay,
            and backoff.
        CONFIRM: Enable confirmation-related execution flags such as forcing or
            skipping confirmation prompts.

    Notes:
        - These values are intended for execution control, not domain-specific
          command input.
        - String values are normalized case-insensitively through `_missing_()`
          so config and user input can be converted into enum members with
          friendlier validation behavior.
    """

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
