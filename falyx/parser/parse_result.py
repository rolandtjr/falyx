# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Root parse result model for the Falyx CLI runtime.

This module defines `RootParseResult`, the normalized output produced by the
root-level Falyx parsing stage.

`RootParseResult` captures the session-scoped state derived from the initial
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

from falyx.mode import FalyxMode


@dataclass(slots=True)
class RootParseResult:
    """Represents the normalized result of root-level Falyx argument parsing.

    `RootParseResult` stores the outcome of the initial CLI parse that occurs at
    the application boundary. It separates session-level runtime settings from
    the remaining argv that should continue into namespace routing and
    command-local parsing.

    This model is used to communicate root parsing decisions cleanly to the
    rest of the Falyx runtime, including whether the application should enter
    help mode or continue with normal command execution.

    Attributes:
        mode: Top-level runtime mode selected from the root parse.
        raw_argv: Original argv passed into the root parser.
        verbose: Whether verbose logging should be enabled for the session.
        debug_hooks: Whether hook execution should be logged in detail.
        never_prompt: Whether prompts should be suppressed for the session.
        remaining_argv: Unconsumed argv that should be forwarded to routed
            command resolution.
        tldr_requested: Whether root TLDR output was requested.
    """

    mode: FalyxMode
    raw_argv: list[str] = field(default_factory=list)
    verbose: bool = False
    debug_hooks: bool = False
    never_prompt: bool = False
    remaining_argv: list[str] = field(default_factory=list)
    tldr_requested: bool = False
