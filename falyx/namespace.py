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
        key: Primary identifier used to enter the namespace.
        description: User-facing description of the namespace.
        namespace: Nested `Falyx` instance activated when this namespace is
            selected.
        aliases: Optional alternate names that may also resolve to the same
            namespace.
        help_text: Optional short help text used in listings or help output.
        style: Rich style used when rendering the namespace key or aliases.
        hidden: Whether the namespace should be omitted from visible menus and
            help listings.
    """

    key: str
    description: str
    namespace: Falyx
    aliases: list[str] = field(default_factory=list)
    help_text: str = ""
    style: str = OneColors.CYAN
    hidden: bool = False
