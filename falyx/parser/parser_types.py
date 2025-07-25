# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Type utilities and argument state models for Falyx's custom CLI argument parser.

This module provides specialized helpers and data structures used by
the `CommandArgumentParser` to handle non-standard parsing behavior.

Contents:
- `true_none` / `false_none`: Type coercion utilities that allow tri-state boolean
  semantics (True, False, None). These are especially useful for supporting
  `--flag` / `--no-flag` optional booleans in CLI arguments.
- `ArgumentState`: Tracks whether an `Argument` has been consumed during parsing.
- `TLDRExample`: A structured example for showing usage snippets and descriptions,
   used in TLDR views.

These tools support richer expressiveness and user-friendly ergonomics in
Falyx's declarative command-line interfaces.
"""
from dataclasses import dataclass
from typing import Any

from falyx.parser.argument import Argument


@dataclass
class ArgumentState:
    """Tracks an argument and whether it has been consumed."""

    arg: Argument
    consumed: bool = False


@dataclass(frozen=True)
class TLDRExample:
    """Represents a usage example for TLDR output."""

    usage: str
    description: str


def true_none(value: Any) -> bool | None:
    """Return True if value is not None, else None."""
    if value is None:
        return None
    return True


def false_none(value: Any) -> bool | None:
    """Return False if value is not None, else None."""
    if value is None:
        return None
    return False
