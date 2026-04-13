# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Root parsing models and helpers for the Falyx CLI runtime.

This module defines the minimal parsing layer used before namespace routing and
command-local argument parsing begin.

It provides:

- `RootOptions`, a lightweight container for session-scoped flags such as
  verbose logging, help, TLDR, and prompt suppression.
- `FalyxParser`, a small root parser that consumes only leading global options
  from argv and leaves the remaining tokens untouched for downstream routing.

Unlike `CommandArgumentParser`, this module does not parse command-specific
arguments or attempt to resolve leaf-command inputs. Its responsibility is
intentionally narrow: identify root-level flags, determine the initial
application mode, and normalize the result into a `RootParseResult`.

Parsing behavior is prefix-based. Root flags are consumed only from the start of
argv, and parsing stops at the first non-root token or an explicit `--`
separator. This allows the remaining arguments to be preserved exactly for later
namespace resolution and command-local parsing.

Typical flow:
    1. Raw argv is passed to `FalyxParser.parse()`.
    2. Leading root/session flags are extracted into `RootOptions`.
    3. A `RootParseResult` is returned with either:
       - `FalyxMode.HELP` when root help or TLDR was requested, or
       - `FalyxMode.COMMAND` when normal routed execution should continue.
    4. Remaining argv is forwarded unchanged to the main Falyx routing layer.

This module serves as the root-entry parsing boundary for Falyx applications.
"""
from __future__ import annotations

from dataclasses import dataclass

from falyx.mode import FalyxMode
from falyx.parser.parse_result import RootParseResult


@dataclass(slots=True)
class RootOptions:
    """Container for root-level Falyx session flags.

    `RootOptions` stores the boolean flags recognized at the application
    boundary before namespace routing and command-local parsing begin. These
    values represent session-scoped behavior that applies to the overall Falyx
    runtime rather than to any individual command.

    The model is intentionally small and lightweight. It is produced by
    `FalyxParser._parse_root_options()` and then translated into a
    `RootParseResult` that drives the initial execution mode and runtime
    configuration.

    Attributes:
        verbose: Whether verbose logging should be enabled for the session.
        debug_hooks: Whether hook execution should be logged in detail.
        never_prompt: Whether prompts should be suppressed for the session.
        help: Whether root help output was requested.
        tldr: Whether root TLDR output was requested.
    """

    verbose: bool = False
    debug_hooks: bool = False
    never_prompt: bool = False
    help: bool = False
    tldr: bool = False


class FalyxParser:
    """Parse root-level Falyx CLI flags into an initial runtime result.

    `FalyxParser` is the narrow, top-level parser used before namespace routing
    and command-local argument parsing begin. Its job is to inspect only the
    leading session-scoped flags in argv, determine the initial application
    mode, and return a normalized `RootParseResult`.

    Responsibilities:
        - Parse only root/session flags such as verbose logging, help, TLDR,
          and prompt suppression.
        - Stop parsing at the first non-root token or explicit `--` separator.
        - Preserve the remaining argv exactly for downstream routing.
        - Translate root help or TLDR requests into `FalyxMode.HELP`.
        - Translate normal execution into `FalyxMode.COMMAND`.

    Design Notes:
        - This parser does not resolve commands or namespaces.
        - This parser does not parse command-specific arguments.
        - Command-local parsing is delegated later to `CommandArgumentParser`
          after Falyx routing has identified a leaf command.
        - Root parsing is intentionally prefix-only so session flags apply at
          the application boundary without mutating command-local argv.

    Typical Usage:
        `Falyx.run()` or another top-level entrypoint passes raw argv into
        `FalyxParser.parse()`, applies the returned session options, and then
        forwards the untouched remaining argv into the routed Falyx execution
        flow.

    Attributes:
        ROOT_FLAG_ALIASES: Mapping of recognized root CLI flags to
            `RootOptions` attribute names.
    """

    ROOT_FLAG_ALIASES: dict[str, str] = {
        "-n": "never_prompt",
        "--never-prompt": "never_prompt",
        "-v": "verbose",
        "--verbose": "verbose",
        "-d": "debug_hooks",
        "--debug-hooks": "debug_hooks",
        "?": "help",
        "-h": "help",
        "--help": "help",
        "-T": "tldr",
        "--tldr": "tldr",
    }

    @classmethod
    def _parse_root_options(
        cls,
        argv: list[str],
    ) -> tuple[RootOptions, list[str]]:
        """Parse only root/session flags from the start of argv.

        Parsing stops at the first token that is not a recognized root flag.
        Remaining tokens are returned untouched for later routing.

        Examples:
            ["--verbose", "deploy", "--env", "prod"]
                -> (RootOptions(verbose=True), ["deploy", "--env", "prod"])

            ["deploy", "--verbose"]
                -> (RootOptions(), ["deploy", "--verbose"])
        """
        options = RootOptions()
        remaining_start = 0

        for index, token in enumerate(argv):
            if token == "--":
                remaining_start = index + 1
                break

            attr = cls.ROOT_FLAG_ALIASES.get(token)
            if attr is None:
                remaining_start = index
                break

            setattr(options, attr, True)
        else:
            remaining_start = len(argv)

        remaining = argv[remaining_start:]
        return options, remaining

    @classmethod
    def parse(cls, argv: list[str] | None = None) -> RootParseResult:
        argv = argv or []
        root, remaining = cls._parse_root_options(argv)

        if root.help or root.tldr:
            return RootParseResult(
                mode=FalyxMode.HELP,
                raw_argv=argv,
                never_prompt=root.never_prompt,
                verbose=root.verbose,
                debug_hooks=root.debug_hooks,
                tldr_requested=root.tldr,
            )

        return RootParseResult(
            mode=FalyxMode.COMMAND,
            raw_argv=argv,
            verbose=root.verbose,
            debug_hooks=root.debug_hooks,
            never_prompt=root.never_prompt,
            remaining_argv=remaining,
        )
