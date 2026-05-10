# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Namespace entry model for nested Falyx applications.

This module defines `FalyxNamespace`, the lightweight metadata container used to
register one `Falyx` instance inside another as a routed namespace entry.

A `FalyxNamespace` describes how a nested application should appear and behave
from the perspective of its parent namespace. It stores the public-facing key,
description, aliases, styling, and visibility flags used for routing,
completion, help rendering, and menu display, while holding a reference to the
child `Falyx` runtime that should take over once the namespace is entered.

This model is intentionally small and declarative. It does not implement
routing, rendering, or execution itself; those responsibilities remain with the
parent and child `Falyx` instances.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.style import StyleType

from falyx.context import InvocationContext
from falyx.themes import OneColors

if TYPE_CHECKING:
    from falyx.falyx import Falyx


@dataclass
class FalyxNamespace:
    """Represents a nested `Falyx` application exposed as a namespace entry.

    `FalyxNamespace` is used by a parent `Falyx` instance to register and
    describe a child `Falyx` runtime as a routable namespace. It provides the
    metadata needed to expose that child namespace consistently across command
    resolution, completion, help output, and menu rendering.

    Attributes:
        key (str): Primary identifier used to enter the namespace.
        description (str): User-facing namespace description.
        namespace (Falyx): Nested `Falyx` instance activated when this namespace is
            selected.
        aliases (list[str]): Optional alternate names that may also resolve to the same
            namespace.
        help_text (str): Optional short help text used in listings or help output.
        style (StyleType): Rich style used when rendering the namespace key or aliases.
        hidden (bool): Whether the namespace should be omitted from visible menus and
            help listings.
    """

    key: str
    description: str
    namespace: Falyx
    aliases: list[str] = field(default_factory=list)
    help_text: str = ""
    style: StyleType = OneColors.CYAN
    hidden: bool = False

    def get_help_signature(
        self, invocation_context: InvocationContext
    ) -> tuple[str, str, str | None]:
        """Returns the usage signature for this namespace, used in help rendering."""
        usage = f"{self.key} {self.namespace._get_usage_fragment(invocation_context)}"
        if self.aliases:
            usage += f" (aliases: {', '.join(self.aliases)})"
        return usage, self.description, self.help_text
