# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""validators.py"""
from typing import KeysView, Sequence

from prompt_toolkit.validation import Validator


def int_range_validator(minimum: int, maximum: int) -> Validator:
    """Validator for integer ranges."""

    def validate(text: str) -> bool:
        try:
            value = int(text)
            if not minimum <= value <= maximum:
                return False
            return True
        except ValueError:
            return False

    return Validator.from_callable(
        validate,
        error_message=f"Invalid input. Enter a number between {minimum} and {maximum}.",
    )


def key_validator(keys: Sequence[str] | KeysView[str]) -> Validator:
    """Validator for key inputs."""

    def validate(text: str) -> bool:
        if text.upper() not in [key.upper() for key in keys]:
            return False
        return True

    return Validator.from_callable(
        validate, error_message=f"Invalid input. Available keys: {', '.join(keys)}."
    )


def yes_no_validator() -> Validator:
    """Validator for yes/no inputs."""

    def validate(text: str) -> bool:
        if text.upper() not in ["Y", "N"]:
            return False
        return True

    return Validator.from_callable(validate, error_message="Enter 'Y' or 'n'.")
