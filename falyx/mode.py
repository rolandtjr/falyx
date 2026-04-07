# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""Defines `FalyxMode`, an enum representing the different modes of operation for Falyx."""
from enum import Enum


class FalyxMode(Enum):
    MENU = "menu"
    COMMAND = "command"
    PREVIEW = "preview"
    HELP = "help"
    ERROR = "error"
