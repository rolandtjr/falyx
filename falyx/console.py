# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Global console instance for Falyx CLI applications."""
from rich.console import Console

from falyx.exceptions import FalyxError
from falyx.themes import OneColors, get_nord_theme

console = Console(color_system="truecolor", theme=get_nord_theme())
error_console = Console(color_system="truecolor", theme=get_nord_theme(), stderr=True)


def print_error(
    message: str | Exception,
    *,
    hint: str | None = None,
) -> None:
    if hint is None and isinstance(message, FalyxError):
        hint = message.hint

    error_console.print(f"[{OneColors.DARK_RED}]error:[/] {message}")
    if hint:
        error_console.print(f"[{OneColors.LIGHT_YELLOW}]hint:[/] {hint}")
