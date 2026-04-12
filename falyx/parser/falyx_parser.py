# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from falyx.mode import FalyxMode
from falyx.parser.parse_result import RootParseResult


@dataclass(slots=True)
class RootOptions:
    verbose: bool = False
    debug_hooks: bool = False
    never_prompt: bool = False
    help: bool = False
    tldr: bool = False


class FalyxParser:
    """Root parser and command router for Falyx.

    Responsibilities:
    - parse global/root flags
    - resolve built-ins vs registered commands
    - normalize CLI input into ParseResult
    - delegate command-specific parsing to CommandArgumentParser
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
