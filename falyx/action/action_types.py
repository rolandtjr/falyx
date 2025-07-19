# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines strongly-typed enums used throughout the Falyx CLI framework for
representing common structured values like file formats, selection return types,
and confirmation modes.

These enums support alias resolution, graceful coercion from string inputs,
and are used for input validation, serialization, and CLI configuration parsing.

Exports:
- FileType: Defines supported file formats for `LoadFileAction` and `SaveFileAction`
- SelectionReturnType: Defines structured return modes for `SelectionAction`
- ConfirmType: Defines selectable confirmation types for prompts and guards

Key Features:
- Custom `_missing_()` methods for forgiving string coercion and error reporting
- Aliases and normalization support for user-friendly config-driven workflows
- Useful in CLI flag parsing, YAML configs, and dynamic schema validation

Example:
    FileType("yml") → FileType.YAML
    SelectionReturnType("value") → SelectionReturnType.VALUE
    ConfirmType("YES_NO") → ConfirmType.YES_NO
"""
from __future__ import annotations

from enum import Enum


class FileType(Enum):
    """
    Represents supported file types for reading and writing in Falyx Actions.

    Used by `LoadFileAction` and `SaveFileAction` to determine how to parse or
    serialize file content. Includes alias resolution for common extensions like
    `.yml`, `.txt`, and `filepath`.

    Members:
        TEXT: Raw encoded text as a string.
        PATH: Returns the file path (as a Path object).
        JSON: JSON-formatted object.
        TOML: TOML-formatted object.
        YAML: YAML-formatted object.
        CSV: List of rows (as lists) from a CSV file.
        TSV: Same as CSV, but tab-delimited.
        XML: Raw XML as a ElementTree.

    Example:
        FileType("yml")  → FileType.YAML
    """

    TEXT = "text"
    PATH = "path"
    JSON = "json"
    TOML = "toml"
    YAML = "yaml"
    CSV = "csv"
    TSV = "tsv"
    XML = "xml"

    @classmethod
    def choices(cls) -> list[FileType]:
        """Return a list of all hook type choices."""
        return list(cls)

    @classmethod
    def _get_alias(cls, value: str) -> str:
        aliases = {
            "yml": "yaml",
            "txt": "text",
            "file": "path",
            "filepath": "path",
        }
        return aliases.get(value, value)

    @classmethod
    def _missing_(cls, value: object) -> FileType:
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
        """Return the string representation of the confirm type."""
        return self.value


class SelectionReturnType(Enum):
    """
    Controls what is returned from a `SelectionAction` when using a selection map.

    Determines how the user's choice(s) from a `dict[str, SelectionOption]` are
    transformed and returned by the action.

    Members:
        KEY: Return the selected key(s) only.
        VALUE: Return the value(s) associated with the selected key(s).
        DESCRIPTION: Return the description(s) of the selected item(s).
        DESCRIPTION_VALUE: Return a dict of {description: value} pairs.
        ITEMS: Return full `SelectionOption` objects as a dict {key: SelectionOption}.

    Example:
        return_type=SelectionReturnType.VALUE  → returns raw values like 'prod'
    """

    KEY = "key"
    VALUE = "value"
    DESCRIPTION = "description"
    DESCRIPTION_VALUE = "description_value"
    ITEMS = "items"

    @classmethod
    def choices(cls) -> list[SelectionReturnType]:
        """Return a list of all hook type choices."""
        return list(cls)

    @classmethod
    def _get_alias(cls, value: str) -> str:
        aliases = {
            "desc": "description",
            "desc_value": "description_value",
        }
        return aliases.get(value, value)

    @classmethod
    def _missing_(cls, value: object) -> SelectionReturnType:
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
        """Return the string representation of the confirm type."""
        return self.value


class ConfirmType(Enum):
    """
    Enum for defining prompt styles in confirmation dialogs.

    Used by confirmation actions to control user input behavior and available choices.

    Members:
        YES_NO: Prompt with Yes / No options.
        YES_CANCEL: Prompt with Yes / Cancel options.
        YES_NO_CANCEL: Prompt with Yes / No / Cancel options.
        TYPE_WORD: Require user to type a specific confirmation word (e.g., "delete").
        TYPE_WORD_CANCEL: Same as TYPE_WORD, but allows cancellation.
        OK_CANCEL: Prompt with OK / Cancel options.
        ACKNOWLEDGE: Single confirmation button (e.g., "Acknowledge").

    Example:
        ConfirmType("yes_no_cancel") → ConfirmType.YES_NO_CANCEL
    """

    YES_NO = "yes_no"
    YES_CANCEL = "yes_cancel"
    YES_NO_CANCEL = "yes_no_cancel"
    TYPE_WORD = "type_word"
    TYPE_WORD_CANCEL = "type_word_cancel"
    OK_CANCEL = "ok_cancel"
    ACKNOWLEDGE = "acknowledge"

    @classmethod
    def choices(cls) -> list[ConfirmType]:
        """Return a list of all hook type choices."""
        return list(cls)

    @classmethod
    def _get_alias(cls, value: str) -> str:
        aliases = {
            "yes": "yes_no",
            "ok": "ok_cancel",
            "type": "type_word",
            "word": "type_word",
            "word_cancel": "type_word_cancel",
            "ack": "acknowledge",
        }
        return aliases.get(value, value)

    @classmethod
    def _missing_(cls, value: object) -> ConfirmType:
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
        """Return the string representation of the confirm type."""
        return self.value
