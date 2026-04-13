# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Argument grouping models for the Falyx command argument parser.

This module defines lightweight dataclasses used by
`CommandArgumentParser` to organize arguments into named help sections and
mutually exclusive sets.

It provides:

- `ArgumentGroup`, which represents a logical collection of related argument
  destinations for grouped help rendering.
- `MutuallyExclusiveGroup`, which represents a set of argument destinations
  where only one member may be selected, with optional group-level
  requiredness.

These models are metadata containers only. They do not perform parsing or
validation themselves. Instead, they are populated and enforced by
`CommandArgumentParser` during argument registration, parsing, and help
generation.

This module exists to keep argument-group state explicit, structured, and easy
to introspect.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ArgumentGroup:
    """Represents a named group of related command argument destinations.

    `ArgumentGroup` is used by `CommandArgumentParser` to collect arguments that
    belong together conceptually so they can be rendered under a shared section
    in help output and tracked as a unit in parser metadata.

    This class stores only grouping metadata and does not implement any parsing
    behavior on its own.

    Attributes:
        name: User-facing name of the argument group.
        description: Optional descriptive text for the group, typically used in
            help rendering.
        dests: Destination names of arguments assigned to this group.
    """

    name: str
    description: str = ""
    dests: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MutuallyExclusiveGroup:
    """Represents a mutually exclusive set of argument destinations.

    `MutuallyExclusiveGroup` is used by `CommandArgumentParser` to model groups
    of arguments where only one member may be provided at a time. It can also
    mark the group as required, meaning that exactly one of the grouped
    arguments must be present.

    This class stores group metadata only. Validation and enforcement are
    performed by the parser.

    Attributes:
        name: User-facing name of the mutually exclusive group.
        required: Whether at least one argument in the group must be supplied.
        description: Optional descriptive text for the group, typically used in
            help rendering.
        dests: Destination names of arguments assigned to this mutually
            exclusive group.
    """

    name: str
    required: bool = False
    description: str = ""
    dests: list[str] = field(default_factory=list)
