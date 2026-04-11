from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from falyx.themes import OneColors

if TYPE_CHECKING:
    from falyx.falyx import Falyx


@dataclass
class FalyxNamespace:
    key: str
    description: str
    namespace: Falyx
    aliases: list[str] = field(default_factory=list)
    help_text: str = ""
    style: str = OneColors.CYAN
    hidden: bool = False
