# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""validators.py"""
from typing import KeysView, Sequence

from prompt_toolkit.validation import ValidationError, Validator


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


def words_validator(keys: Sequence[str] | KeysView[str]) -> Validator:
    """Validator for specific word inputs."""

    def validate(text: str) -> bool:
        if text.upper() not in [key.upper() for key in keys]:
            return False
        return True

    return Validator.from_callable(
        validate, error_message=f"Invalid input. Choices: {{{', '.join(keys)}}}."
    )


def word_validator(word: str) -> Validator:
    """Validator for specific word inputs."""

    def validate(text: str) -> bool:
        if text.upper().strip() == "N":
            return True
        return text.upper().strip() == word.upper()

    return Validator.from_callable(validate, error_message=f"Enter '{word}' or 'N'.")


class MultiIndexValidator(Validator):
    def __init__(
        self,
        minimum: int,
        maximum: int,
        number_selections: int | str,
        separator: str,
        allow_duplicates: bool,
        cancel_key: str,
    ) -> None:
        self.minimum = minimum
        self.maximum = maximum
        self.number_selections = number_selections
        self.separator = separator
        self.allow_duplicates = allow_duplicates
        self.cancel_key = cancel_key
        super().__init__()

    def validate(self, document):
        selections = [
            index.strip() for index in document.text.strip().split(self.separator)
        ]
        if not selections or selections == [""]:
            raise ValidationError(message="Select at least 1 item.")
        if self.cancel_key in selections and len(selections) == 1:
            return
        elif self.cancel_key in selections:
            raise ValidationError(message="Cancel key must be selected alone.")
        for selection in selections:
            try:
                index = int(selection)
                if not self.minimum <= index <= self.maximum:
                    raise ValidationError(
                        message=f"Invalid selection: {selection}. Select a number between {self.minimum} and {self.maximum}."
                    )
            except ValueError:
                raise ValidationError(
                    message=f"Invalid selection: {selection}. Select a number between {self.minimum} and {self.maximum}."
                )
            if not self.allow_duplicates and selections.count(selection) > 1:
                raise ValidationError(message=f"Duplicate selection: {selection}")
        if isinstance(self.number_selections, int):
            if self.number_selections == 1 and len(selections) > 1:
                raise ValidationError(message="Invalid selection. Select only 1 item.")
            if len(selections) != self.number_selections:
                raise ValidationError(
                    message=f"Select exactly {self.number_selections} items separated by '{self.separator}'"
                )


class MultiKeyValidator(Validator):
    def __init__(
        self,
        keys: Sequence[str] | KeysView[str],
        number_selections: int | str,
        separator: str,
        allow_duplicates: bool,
        cancel_key: str,
    ) -> None:
        self.keys = keys
        self.separator = separator
        self.number_selections = number_selections
        self.allow_duplicates = allow_duplicates
        self.cancel_key = cancel_key
        super().__init__()

    def validate(self, document):
        selections = [key.strip() for key in document.text.strip().split(self.separator)]
        if not selections or selections == [""]:
            raise ValidationError(message="Select at least 1 item.")
        if self.cancel_key in selections and len(selections) == 1:
            return
        elif self.cancel_key in selections:
            raise ValidationError(message="Cancel key must be selected alone.")
        for selection in selections:
            if selection.upper() not in [key.upper() for key in self.keys]:
                raise ValidationError(message=f"Invalid selection: {selection}")
            if not self.allow_duplicates and selections.count(selection) > 1:
                raise ValidationError(message=f"Duplicate selection: {selection}")
        if isinstance(self.number_selections, int):
            if self.number_selections == 1 and len(selections) > 1:
                raise ValidationError(message="Invalid selection. Select only 1 item.")
            if len(selections) != self.number_selections:
                raise ValidationError(
                    message=f"Select exactly {self.number_selections} items separated by '{self.separator}'"
                )
