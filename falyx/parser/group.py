# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ArgumentGroup:
    name: str
    description: str = ""
    dests: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MutuallyExclusiveGroup:
    name: str
    required: bool = False
    description: str = ""
    dests: list[str] = field(default_factory=list)
