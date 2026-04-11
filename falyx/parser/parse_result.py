# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
from dataclasses import dataclass, field

from falyx.mode import FalyxMode


@dataclass(slots=True)
class RootParseResult:
    mode: FalyxMode
    raw_argv: list[str] = field(default_factory=list)
    verbose: bool = False
    debug_hooks: bool = False
    never_prompt: bool = False
    remaining_argv: list[str] = field(default_factory=list)
