# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Runtime mode definitions for the Falyx CLI framework.

This module defines `FalyxMode`, the enum used to represent the high-level
operating mode of a Falyx application during parsing, routing, rendering, and
execution.

These modes describe the current intent of the runtime rather than any
particular command. They are used throughout Falyx to coordinate behavior such
as whether the application should show an interactive menu, execute a routed
command, render help output, preview a command, or surface an error state.

`FalyxMode` is commonly stored in shared runtime state and passed through
invocation and parsing layers so UI rendering and execution flow remain
consistent across CLI and menu-driven entrypoints.
"""
from enum import Enum


class FalyxMode(Enum):
    """Enumerates the high-level runtime modes used by Falyx.

    `FalyxMode` provides a small set of application-wide states that describe
    how the current invocation should be handled.

    Attributes:
        MENU: Interactive menu mode using Prompt Toolkit input and menu
            rendering.
        COMMAND: Direct command-execution mode for routed CLI or programmatic
            invocation.
        PREVIEW: Non-executing preview mode used to inspect a command before it
            runs.
        HELP: Help-rendering mode for namespace, command, or TLDR output.
        ERROR: Error state used when invocation handling should surface a
            failure condition.
    """

    MENU = "menu"
    COMMAND = "command"
    PREVIEW = "preview"
    HELP = "help"
    ERROR = "error"
