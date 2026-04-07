# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from falyx.mode import FalyxMode

if TYPE_CHECKING:
    from falyx.command import Command


@dataclass(slots=True)
class ParseResult:
    mode: FalyxMode
    raw_argv: list[str] = field(default_factory=list)
    verbose: bool = False
    debug_hooks: bool = False
    never_prompt: bool = False
    command_name: str = ""
    command: Command | None = None
    command_argv: list[str] = field(default_factory=list)
    is_preview: bool = False
    error: str | None = None
