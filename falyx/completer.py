# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""Prompt Toolkit completion support for routed Falyx command input.

This module defines `FalyxCompleter`, the interactive completion layer used by
Falyx menu and prompt-driven CLI sessions. The completer is routing-aware: it
delegates namespace traversal to `Falyx.resolve_completion_route()` and only
hands control to a command's `CommandArgumentParser` after a leaf command has
been identified.

Completion behavior is split into two phases:

1. Namespace completion
   While the user is still selecting a command or namespace entry, completion
   candidates are derived from the active namespace via
   `iter_completion_names`. Namespace-level help flags such as `-h`, `--help`,
   `-T`, and `--tldr` are also suggested when appropriate.

2. Leaf-command completion
   Once routing reaches a concrete command, the remaining argv fragment is
   delegated to `CommandArgumentParser.suggest_next()` so command-specific
   flags, values, choices, and positional suggestions can be surfaced.

The completer also supports preview-prefixed input such as `?deploy`, preserves
shell-safe quoting for suggestions containing whitespace, and integrates
directly with Prompt Toolkit's completion API by yielding `Completion`
instances.

Typical usage:
    session = PromptSession(completer=FalyxCompleter(falyx))
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
    """Prompt Toolkit completer for routed Falyx input.

    `FalyxCompleter` provides context-aware completions for interactive Falyx
    sessions. It first asks the owning `Falyx` instance to resolve the current
    input into a partial completion route. Based on that route, it either:

    - suggests visible entries from the active namespace, or
    - delegates argument completion to the resolved command's argument parser.

    This keeps completion aligned with Falyx's routing model so nested
    namespaces, preview-prefixed commands, and command-local argument parsing
    all behave consistently with actual execution.

    Args:
        falyx (Falyx): Active Falyx application instance used to resolve routes
            and retrieve completion candidates.
    """

    def __init__(self, falyx: Falyx):
        """Initialize the completer with a bound Falyx instance.

        Args:
            falyx (Falyx): Active Falyx application that owns the routing and
                command metadata used for completion.
        """
        self.falyx = falyx

    def get_completions(self, document: Document, complete_event):
        """Yield completions for the current input buffer.

        This method is the main Prompt Toolkit completion entrypoint. It parses
        the text before the cursor, determines whether the user is still routing
        through namespaces or has already reached a leaf command, and then
        yields matching `Completion` objects.

        Behavior:
            - Splits the current input using `shlex.split()`.
            - Detects preview-mode input prefixed with `?`.
            - Separates committed tokens from the active stub under the cursor.
            - Resolves the partial route through `Falyx.resolve_completion_route()`.
            - Suggests namespace entries and namespace help flags while routing.
            - Delegates leaf-command completion to
              `CommandArgumentParser.suggest_next()` once a command is resolved.
            - Preserves shell-safe quoting for suggestions containing spaces.

        Args:
            document (Document): Prompt Toolkit document representing the current
                input buffer and cursor position.
            complete_event: Prompt Toolkit completion event metadata. It is not
                currently inspected directly.

        Yields:
            Completion: Completion candidates appropriate to the current routed
            input state.

        Notes:
            - Invalid shell quoting causes completion to stop silently rather
              than raising.
            - Command-specific completion is only attempted after a concrete leaf
              command has been resolved.
        """
        text = document.text_before_cursor
        try:
            tokens = shlex.split(text)
            cursor_at_end = text.endswith((" ", "\t"))
        except ValueError:
            return

        is_preview = False
        if tokens and tokens[0].startswith("?"):
            is_preview = True
            tokens[0] = tokens[0][1:]

        if cursor_at_end:
            committed_tokens = tokens
            stub = ""
        else:
            committed_tokens = tokens[:-1] if tokens else []
            stub = tokens[-1] if tokens else ""

        context = self.falyx.get_current_invocation_context().model_copy(
            update={"is_preview": is_preview}
        )

        route = self.falyx.resolve_completion_route(
            committed_tokens,
            stub=stub,
            cursor_at_end_of_token=cursor_at_end,
            context=context,
            is_preview=is_preview,
        )

        # Still selecting an entry in the current namespace
        if route.expecting_entry:
            suggestions = self._suggest_namespace_entries(route.namespace, route.stub)

            # Only here should namespace-level help/TLDR be suggested.
            if not route.command and (not route.stub or route.stub.startswith("-")):
                suggestions.extend(
                    flag
                    for flag in ("-h", "--help", "-T", "--tldr")
                    if flag.startswith(route.stub)
                )

            if route.is_preview:
                suggestions = [f"?{s}" for s in suggestions]
                current_stub = f"?{route.stub}" if route.stub else "?"
            else:
                current_stub = route.stub

            yield from self._yield_lcp_completions(suggestions, current_stub)
            return

        # Leaf command: CAP owns the rest
        if not route.command or not route.command.arg_parser:
            return

        leaf_tokens = list(route.leaf_argv)
        if route.stub:
            leaf_tokens.append(route.stub)

        try:
            suggestions = route.command.arg_parser.suggest_next(
                leaf_tokens,
                route.cursor_at_end_of_token,
            )
        except Exception:
            return

        yield from self._yield_lcp_completions(suggestions, route.stub)

    def _suggest_namespace_entries(self, namespace: Falyx, prefix: str) -> list[str]:
        """Return matching visible entry names for a namespace prefix.

        This helper filters the current namespace's visible completion names so
        only entries beginning with the provided prefix are returned. Case of the
        returned value is adjusted to follow the case style of the typed prefix.

        Args:
            namespace (Falyx): Namespace whose entries should be searched for
                completion candidates.
            prefix (str): Current partially typed entry name.

        Returns:
            list[str]: Matching namespace entry keys and aliases.
        """
        results: list[str] = []
        for name in namespace.iter_completion_names:
            if name.upper().startswith(prefix.upper()):
                results.append(name.lower() if prefix.islower() else name)
        return results

    def _ensure_quote(self, text: str) -> str:
        """Quote a completion candidate when it contains whitespace.

        Args:
            text (str): Raw completion candidate.

        Returns:
            str: Shell-safe candidate wrapped in double quotes when needed.
        """
        if " " in text or "\t" in text:
            return f'"{text}"'
        return text

    def _yield_lcp_completions(self, suggestions, stub) -> Iterable[Completion]:
        """Yield completions for the current stub using longest-common-prefix logic.

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

        if not suggestions:
            return

        matches = list(dict.fromkeys(s for s in suggestions if s.startswith(stub)))
        if not matches:
            return

        lcp = os.path.commonprefix(matches)

        if len(matches) == 1:
            match = matches[0]
            yield Completion(
                self._ensure_quote(match),
                start_position=-len(stub),
                display=match,
            )
            return

        if len(lcp) > len(stub) and not lcp.startswith("-"):
            yield Completion(
                self._ensure_quote(lcp),
                start_position=-len(stub),
                display=lcp,
            )

        for match in matches:
            yield Completion(
                self._ensure_quote(match),
                start_position=-len(stub),
                display=match,
            )
