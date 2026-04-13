# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Routing result models for the Falyx CLI framework.

This module defines the core types used to describe the outcome of namespace
routing in a `Falyx` application.

It provides:

- `RouteKind`, an enum describing the kind of routed target that was reached,
  such as a leaf command, namespace help, namespace TLDR, namespace menu, or
  an unknown entry.
- `RouteResult`, a structured value object that captures the resolved routing
  state, including the active namespace, invocation context, optional leaf
  command, remaining argv for command-local parsing, and any suggestions for
  unresolved input.

These types sit at the boundary between routing and execution. They do not
perform routing themselves. Instead, they are produced by Falyx routing logic
and then consumed by help rendering, completion, validation, preview, and
command dispatch flows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from falyx.context import InvocationContext
from falyx.namespace import FalyxNamespace

if TYPE_CHECKING:
    from falyx.command import Command
    from falyx.falyx import Falyx


class RouteKind(Enum):
    """Enumerates the possible outcomes of Falyx namespace routing.

    `RouteKind` identifies what the routing layer resolved the current input
    to, allowing downstream code to decide whether it should execute a command,
    render namespace help, show TLDR output, display a namespace menu, or
    surface an unknown-entry message.

    Attributes:
        COMMAND: Routing reached a leaf command that may be parsed and executed.
        NAMESPACE_MENU: Routing stopped at a namespace menu target.
        NAMESPACE_HELP: Routing resolved to namespace help output.
        NAMESPACE_TLDR: Routing resolved to namespace TLDR output.
        UNKNOWN: Routing failed to resolve the requested entry.
    """

    COMMAND = "command"
    NAMESPACE_MENU = "namespace_menu"
    NAMESPACE_HELP = "namespace_help"
    NAMESPACE_TLDR = "namespace_tldr"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class RouteResult:
    """Represents the resolved output of a Falyx routing operation.

    `RouteResult` captures the full state needed after namespace resolution
    completes and before command execution or help rendering begins. It records
    what kind of target was reached, where routing ended, the invocation path
    used to reach it, and any leaf-command metadata needed for downstream
    parsing.

    This model is used by Falyx execution, help, preview, completion, and
    validation flows to make routing decisions explicit and easy to inspect.

    Attributes:
        kind: The type of routed result that was resolved.
        namespace: The `Falyx` namespace where routing ended.
        context: Invocation context describing the routed path and current mode.
        command: Resolved leaf command, if routing ended at a command.
        namespace_entry: Resolved namespace entry, if the route corresponds to a
            specific nested namespace.
        leaf_argv: Remaining argv that should be delegated to the resolved
            command's local parser.
        suggestions: Suggested entry names for unresolved input.
        is_preview: Whether the routed invocation is in preview mode.
    """

    kind: RouteKind
    namespace: "Falyx"
    context: InvocationContext
    command: "Command | None" = None
    namespace_entry: FalyxNamespace | None = None
    leaf_argv: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    is_preview: bool = False
