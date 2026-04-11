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
    COMMAND = "command"
    NAMESPACE_MENU = "namespace_menu"
    NAMESPACE_HELP = "namespace_help"
    NAMESPACE_TLDR = "namespace_tldr"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class RouteResult:
    kind: RouteKind
    namespace: "Falyx"
    context: InvocationContext
    command: "Command | None" = None
    namespace_entry: FalyxNamespace | None = None
    leaf_argv: list[str] = field(default_factory=list)
    typed_path: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    is_preview: bool = False
