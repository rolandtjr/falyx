# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Provides `FalyxCompleter`, an intelligent autocompletion engine for Falyx CLI
menus using Prompt Toolkit.

This completer supports:
- Command key and alias completion (e.g. `R`, `HELP`, `X`)
- Argument flag completion for registered commands (e.g. `--tag`, `--name`)
- Context-aware suggestions based on cursor position and argument structure
- Interactive value completions (e.g. choices and suggestions defined per argument)
- File/path-friendly behavior, quoting completions with spaces automatically


Completions are generated from:
- Registered commands in `Falyx`
- Argument metadata and `suggest_next()` from `CommandArgumentParser`


Integrated with the `Falyx.prompt_session` to enhance the interactive experience.
"""

from __future__ import annotations

import os
import shlex
from typing import TYPE_CHECKING, Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

if TYPE_CHECKING:
    from falyx import Falyx


class FalyxCompleter(Completer):
    """
    Prompt Toolkit completer for Falyx CLI command input.

    This completer provides real-time, context-aware suggestions for:
    - Command keys and aliases (resolved via Falyx._name_map)
    - CLI argument flags and values for each command
    - Suggestions and choices defined in the associated CommandArgumentParser

    It leverages `CommandArgumentParser.suggest_next()` to compute valid completions
    based on current argument state, including:
        - Remaining required or optional flags
        - Flag value suggestions (choices or custom completions)
        - Next positional argument hints
        - Inserts longest common prefix (LCP) completions when applicable
        - Handles special cases like quoted strings and spaces
        - Supports dynamic argument suggestions (e.g. flags, file paths, etc.)

    Args:
        falyx (Falyx): The active Falyx instance providing command and parser context.
    """

    def __init__(self, falyx: "Falyx"):
        self.falyx = falyx

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """
        Compute completions for the current user input.

        Analyzes the input buffer, determines whether the user is typing:
        • A command key/alias
        • A flag/option
        • An argument value

        and yields appropriate completions.

        Args:
            document (Document): The current Prompt Toolkit document (input buffer & cursor).
            complete_event: The triggering event (TAB key, menu display, etc.) — not used here.

        Yields:
            Completion: One or more completions matching the current stub text.
        """
        text = document.text_before_cursor
        try:
            tokens = shlex.split(text)
            cursor_at_end_of_token = document.text_before_cursor.endswith((" ", "\t"))
        except ValueError:
            return

        if not tokens or (len(tokens) == 1 and not cursor_at_end_of_token):
            # Suggest command keys and aliases
            stub = tokens[0] if tokens else ""
            suggestions = [c.text for c in self._suggest_commands(stub)]
            yield from self._yield_lcp_completions(suggestions, stub)
            return

        # Identify command
        command_key = tokens[0].upper()
        command = self.falyx._name_map.get(command_key)
        if not command or not command.arg_parser:
            return

        # If at end of token, e.g., "--t" vs "--tag ", add a stub so suggest_next sees it
        parsed_args = tokens[1:] if cursor_at_end_of_token else tokens[1:-1]
        stub = "" if cursor_at_end_of_token else tokens[-1]

        try:
            suggestions = command.arg_parser.suggest_next(
                parsed_args + ([stub] if stub else []), cursor_at_end_of_token
            )
            yield from self._yield_lcp_completions(suggestions, stub)
        except Exception:
            return

    def _suggest_commands(self, prefix: str) -> Iterable[Completion]:
        """
        Suggest top-level command keys and aliases based on the given prefix.

        Filters all known commands (and `exit`, `help`, `history` built-ins)
        to only those starting with the given prefix.

        Args:
            prefix (str): The current typed prefix.

        Yields:
            Completion: Matching keys or aliases from all registered commands.
        """
        keys = [self.falyx.exit_command.key]
        keys.extend(self.falyx.exit_command.aliases)
        if self.falyx.history_command:
            keys.append(self.falyx.history_command.key)
            keys.extend(self.falyx.history_command.aliases)
        if self.falyx.help_command:
            keys.append(self.falyx.help_command.key)
            keys.extend(self.falyx.help_command.aliases)
        for cmd in self.falyx.commands.values():
            keys.append(cmd.key)
            keys.extend(cmd.aliases)
        for key in keys:
            if key.upper().startswith(prefix):
                yield Completion(key.upper(), start_position=-len(prefix))
            elif key.lower().startswith(prefix):
                yield Completion(key.lower(), start_position=-len(prefix))

    def _ensure_quote(self, text: str) -> str:
        """
        Ensure that a suggestion is shell-safe by quoting if needed.

        Adds quotes around completions containing whitespace so they can
        be inserted into the CLI without breaking tokenization.

        Args:
            text (str): The input text to quote.

        Returns:
            str: The quoted text, suitable for shell command usage.
        """
        if " " in text or "\t" in text:
            return f'"{text}"'
        return text

    def _yield_lcp_completions(self, suggestions, stub):
        """
        Yield completions for the current stub using longest-common-prefix logic.

        Behavior:
        - If only one match → yield it fully.
        - If multiple matches share a longer prefix → insert the prefix, but also
            display all matches in the menu.
        - If no shared prefix → list all matches individually.

        Args:
            suggestions (list[str]): The raw suggestions to consider.
            stub (str): The currently typed prefix (used to offset insertion).

        Yields:
            Completion: Completion objects for the Prompt Toolkit menu.
        """
        matches = [s for s in suggestions if s.startswith(stub)]
        if not matches:
            return

        lcp = os.path.commonprefix(matches)

        if len(matches) == 1:
            yield Completion(
                self._ensure_quote(matches[0]),
                start_position=-len(stub),
                display=matches[0],
            )
        elif len(lcp) > len(stub) and not lcp.startswith("-"):
            yield Completion(lcp, start_position=-len(stub), display=lcp)
            for match in matches:
                yield Completion(
                    self._ensure_quote(match), start_position=-len(stub), display=match
                )
        else:
            for match in matches:
                yield Completion(
                    self._ensure_quote(match), start_position=-len(stub), display=match
                )
