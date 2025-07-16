# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""action_types.py"""
from __future__ import annotations

from enum import Enum


class FileType(Enum):
    """Enum for file return types."""

    TEXT = "text"
    PATH = "path"
    JSON = "json"
    TOML = "toml"
    YAML = "yaml"
    CSV = "csv"
    TSV = "tsv"
    XML = "xml"

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
        if isinstance(value, str):
            normalized = value.lower()
            alias = cls._get_alias(normalized)
            for member in cls:
                if member.value == alias:
                    return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid FileType: '{value}'. Must be one of: {valid}")


class SelectionReturnType(Enum):
    """Enum for dictionary return types."""

    KEY = "key"
    VALUE = "value"
    DESCRIPTION = "description"
    DESCRIPTION_VALUE = "description_value"
    ITEMS = "items"

    @classmethod
    def _missing_(cls, value: object) -> SelectionReturnType:
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid DictReturnType: '{value}'. Must be one of: {valid}")


class ConfirmType(Enum):
    """Enum for different confirmation types."""

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

    def __str__(self) -> str:
        """Return the string representation of the confirm type."""
        return self.value

    @classmethod
    def _missing_(cls, value: object) -> ConfirmType:
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower():
                    return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid ConfirmType: '{value}'. Must be one of: {valid}")
