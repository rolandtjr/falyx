# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Provides `FalyxCompleter`, an intelligent autocompletion engine for Falyx CLI
menus using Prompt Toolkit.

This completer supports:
- Command key and alias completion (e.g. `R`, `HELP`, `X`)
- Argument flag completion for registered commands (e.g. `--tag`, `--name`)
- Context-aware suggestions based on cursor position and argument structure
- Interactive value completions (e.g. choices and suggestions defined per argument)

Completions are sourced from `CommandArgumentParser.suggest_next`, which analyzes
parsed tokens to determine appropriate next arguments, flags, or values.

Integrated with the `Falyx.prompt_session` to enhance the interactive experience.
"""

from __future__ import annotations

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

    Args:
        falyx (Falyx): The Falyx menu instance containing all command mappings and parsers.
    """

    def __init__(self, falyx: "Falyx"):
        self.falyx = falyx

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """
        Yield completions based on the current document input.

        Args:
            document (Document): The prompt_toolkit document containing the input buffer.
            complete_event: The completion trigger event (unused).

        Yields:
            Completion objects matching command keys or argument suggestions.
        """
        text = document.text_before_cursor
        try:
            tokens = shlex.split(text)
            cursor_at_end_of_token = document.text_before_cursor.endswith((" ", "\t"))
        except ValueError:
            return

        if not tokens or (len(tokens) == 1 and not cursor_at_end_of_token):
            # Suggest command keys and aliases
            yield from self._suggest_commands(tokens[0] if tokens else "")
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
            if not command.arg_parser:
                return
            suggestions = command.arg_parser.suggest_next(
                parsed_args + ([stub] if stub else []), cursor_at_end_of_token
            )
            for suggestion in suggestions:
                if suggestion.startswith(stub):
                    yield Completion(suggestion, start_position=-len(stub))
        except Exception:
            return

    def _suggest_commands(self, prefix: str) -> Iterable[Completion]:
        """
        Suggest top-level command keys and aliases based on the given prefix.

        Args:
            prefix (str): The user input to match against available commands.

        Yields:
            Completion: Matching keys or aliases from all registered commands.
        """
        prefix = prefix.upper()
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
                yield Completion(key, start_position=-len(prefix))
