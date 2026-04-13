# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Completion route models for routed Falyx autocompletion.

This module defines `CompletionRoute`, a lightweight value object used by the
Falyx completion system to describe the partially resolved state of interactive
input during autocompletion.

`CompletionRoute` sits at the boundary between namespace routing and
command-local argument completion. It captures enough information for the
completer to determine whether it should continue suggesting namespace entries
or delegate to a resolved command's argument parser.

Typical usage:
    - A user types part of a namespace path or command key.
    - Falyx resolves as much of that path as possible.
    - The resulting `CompletionRoute` describes the active namespace, any
      resolved leaf command, the remaining argv fragment, and the current
      token stub under the cursor.
    - `FalyxCompleter` uses this information to decide what completions to
      surface next.

This module is intentionally small and focused. It does not perform routing or
completion itself; it only models the routed state needed by the completer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from falyx.context import InvocationContext

if TYPE_CHECKING:
    from falyx.command import Command
    from falyx.falyx import Falyx


@dataclass(slots=True)
class CompletionRoute:
    """Represents a partially resolved route used during autocompletion.

    A `CompletionRoute` describes the current routed state of user input while
    Falyx is generating interactive completions. It distinguishes between two
    broad states:

    - namespace-routing state, where the user is still selecting a visible entry
      within the current namespace
    - leaf-command state, where a concrete command has been resolved and the
      remaining input should be completed by that command's argument parser

    Attributes:
        namespace (Falyx): The active namespace in which completion is currently
            taking place.
        context (InvocationContext): Invocation-path context used to preserve the
            routed command path and render context-aware help or usage text.
        command (Command | None): The resolved leaf command, if routing has
            already reached a concrete command. Remains `None` while the user is
            still navigating namespaces.
        leaf_argv (list[str]): Remaining command-local argv tokens that belong to
            the resolved leaf command. These are typically passed to the
            command's argument parser for completion.
        stub (str): The current token fragment under the cursor. This is the
            partial text that completion candidates should replace or extend.
        cursor_at_end_of_token (bool): Whether the cursor is positioned at the
            end of a completed token boundary, such as immediately after a
            trailing space.
        expecting_entry (bool): Whether completion should suggest namespace
            entries rather than command-local arguments.
        is_preview (bool): Whether the input is in preview mode, such as when
            the user begins the invocation with `?`.

    Notes:
        - This model is completion-only and is intentionally separate from
          full execution routing types such as `RouteResult`.
        - `CompletionRoute` does not validate or parse command arguments; it
          only records the routed state needed to decide what should complete
          next.
    """

    namespace: Falyx
    context: InvocationContext
    command: Command | None = None
    leaf_argv: list[str] = field(default_factory=list)
    stub: str = ""
    cursor_at_end_of_token: bool = False
    expecting_entry: bool = False
    is_preview: bool = False
