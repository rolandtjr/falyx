# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from typing import TYPE_CHECKING

from falyx.mode import FalyxMode
from falyx.parser.parse_result import ParseResult

if TYPE_CHECKING:
    from falyx.command import Command
    from falyx.falyx import Falyx


@dataclass(slots=True)
class RootOptions:
    verbose: bool = False
    debug_hooks: bool = False
    never_prompt: bool = False
    version: bool = False
    help: bool = False


class FalyxParser:
    """Root parser and command router for Falyx.

    Responsibilities:
    - parse global/root flags
    - resolve built-ins vs registered commands
    - normalize CLI input into ParseResult
    - delegate command-specific parsing to CommandArgumentParser
    """

    ROOT_FLAG_ALIASES: dict[str, str] = {
        "--never-prompt": "never_prompt",
        "-v": "verbose",
        "--verbose": "verbose",
        "--debug-hooks": "debug_hooks",
        "?": "help",
        "-h": "help",
        "--help": "help",
    }

    def __init__(self, falyx: Falyx) -> None:
        self.falyx = falyx

    def _parse_root_options(
        self,
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

            attr = self.ROOT_FLAG_ALIASES.get(token)
            if attr is None:
                remaining_start = index
                break

            setattr(options, attr, True)
        else:
            remaining_start = len(argv)

        remaining = argv[remaining_start:]
        return options, remaining

    def resolve_command(self, token: str) -> tuple[Command | None, list[str]]:
        """Resolve a command by key, alias, or unique prefix.

        Returns:
            (command, suggestions)
        """
        normalized = token.upper().strip()
        name_map = self.falyx._name_map

        if normalized in name_map:
            return name_map[normalized], []

        prefix_matches = []
        seen = set()
        for key, command in name_map.items():
            if key.startswith(normalized) and id(command) not in seen:
                prefix_matches.append(command)
                seen.add(id(command))

        if len(prefix_matches) == 1:
            return prefix_matches[0], []

        suggestions = get_close_matches(
            normalized, list(name_map.keys()), n=3, cutoff=0.7
        )
        return None, suggestions

    def _parse_command(
        self,
        argv: list[str],
        root: RootOptions,
        remaining: list[str],
    ) -> ParseResult:
        raw_name = remaining[0]
        is_preview = raw_name.startswith("?")
        command_name = raw_name[1:] if is_preview else raw_name

        command, suggestions = self.resolve_command(command_name)
        if not command:
            sugguestions_text = (
                f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            )
            return ParseResult(
                mode=FalyxMode.ERROR,
                raw_argv=argv,
                command_name=command_name,
                command_argv=remaining[1:],
                verbose=root.verbose,
                debug_hooks=root.debug_hooks,
                never_prompt=root.never_prompt,
                error=f"Unknown command '{command_name}'.{sugguestions_text}",
            )

        command_argv = remaining[1:]

        return ParseResult(
            mode=FalyxMode.COMMAND,
            raw_argv=argv,
            command_name=command_name,
            command=command,
            command_argv=command_argv,
            is_preview=is_preview,
            verbose=root.verbose,
            debug_hooks=root.debug_hooks,
            never_prompt=root.never_prompt,
        )

    def parse(self, argv: list[str] | None = None) -> ParseResult:
        argv = argv or []
        root, remaining = self._parse_root_options(argv)

        if root.help:
            return ParseResult(
                mode=FalyxMode.HELP,
                raw_argv=argv,
                never_prompt=root.never_prompt,
                verbose=root.verbose,
                debug_hooks=root.debug_hooks,
            )

        if not remaining:
            return ParseResult(
                mode=FalyxMode.MENU,
                raw_argv=argv,
                verbose=root.verbose,
                debug_hooks=root.debug_hooks,
                never_prompt=root.never_prompt,
            )

        head, *tail = remaining

        return self._parse_command(argv, root, remaining)
