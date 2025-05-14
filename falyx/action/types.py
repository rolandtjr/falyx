from __future__ import annotations

from enum import Enum


class FileReturnType(Enum):
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
    def _missing_(cls, value: object) -> FileReturnType:
        if isinstance(value, str):
            normalized = value.lower()
            alias = cls._get_alias(normalized)
            for member in cls:
                if member.value == alias:
                    return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid FileReturnType: '{value}'. Must be one of: {valid}")
