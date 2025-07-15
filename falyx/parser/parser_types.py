# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""parser_types.py"""
from typing import Any


def true_none(value: Any) -> bool | None:
    if value is None:
        return None
    return True


def false_none(value: Any) -> bool | None:
    if value is None:
        return None
    return False
