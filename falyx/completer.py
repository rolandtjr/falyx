from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

if TYPE_CHECKING:
    from falyx import Falyx


class FalyxCompleter(Completer):
    """Completer for Falyx commands."""

    def __init__(self, falyx: "Falyx"):
        self.falyx = falyx

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
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

    def _suggest_commands(self, prefix: str) -> Iterable[Completion]:
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
