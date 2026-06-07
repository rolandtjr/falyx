# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Parse result model for the Falyx CLI runtime.

This module defines `ParseResult`, the normalized output produced by the
root-level Falyx parsing stage.

`ParseResult` captures the session-scoped state derived from the initial
CLI parse before namespace routing or command-local argument parsing begins. It
records the selected top-level mode, the original argv, root option flags, and
any remaining argv that should be forwarded into the routed execution layer.

This model is typically produced by `FalyxParser.parse()` and then consumed by
higher-level Falyx runtime entrypoints such as `Falyx.run()` to configure
logging, prompt behavior, help rendering, and routed command dispatch.

The dataclass is intentionally lightweight and focused on root parsing only. It
does not perform parsing, validation, or execution itself.
"""
from dataclasses import dataclass, field
from typing import Any

from falyx.mode import FalyxMode


@dataclass(slots=True)
class ParseResult:
    """Represents the normalized result of root-level Falyx argument parsing.

    `ParseResult` stores the outcome of the initial CLI parse that occurs at
    the application boundary. It separates session-level runtime settings from
    the remaining argv that should continue into namespace routing and
    command-local parsing.

    This model is used to communicate root parsing decisions cleanly to the
    rest of the Falyx runtime, including whether the application should enter
    help mode or continue with normal command execution.

    Attributes:
        mode: Top-level runtime mode selected from the root parse.
        raw_argv: Original argv passed into the root parser.
        root_defaults: Dictionary of parsed root-level options and their default values.
        root_options: Dictionary of parsed root-level options that should be
            applied at the root level for all namespaces.
        namespace_defaults: Dictionary of parsed namespace-level options and their default values.
        namespace_options: Dictionary of parsed namespace-level options and their values.
        remaining_argv: Unconsumed argv that should be forwarded to routed
            command resolution.
        current_head: The current head token being processed (for error reporting).
        help: Whether help output was requested at the root level.
        tldr: Whether TLDR output was requested at the root level.
        verbose: Whether verbose logging should be enabled for the session.
        debug_hooks: Whether hook execution should be logged in detail.
        never_prompt: Whether prompts should be suppressed for the session.
    """

    mode: FalyxMode
    raw_argv: list[str] = field(default_factory=list)
    root_defaults: dict[str, Any] = field(default_factory=dict)
    root_options: dict[str, Any] = field(default_factory=dict)
    namespace_defaults: dict[str, Any] = field(default_factory=dict)
    namespace_options: dict[str, Any] = field(default_factory=dict)
    remaining_argv: list[str] = field(default_factory=list)
    current_head: str = ""
    help: bool = False
    tldr: bool = False
