# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Utilities for custom type coercion in Falyx argument parsing.

Provides special-purpose converters used to support optional boolean flags and
other non-standard argument behaviors within the Falyx CLI parser system.
"""
from typing import Any


def true_none(value: Any) -> bool | None:
    if value is None:
        return None
    return True


def false_none(value: Any) -> bool | None:
    if value is None:
        return None
    return False
