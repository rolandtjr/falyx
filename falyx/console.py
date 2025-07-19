# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""Global console instance for Falyx CLI applications."""
from rich.console import Console

from falyx.themes import get_nord_theme

console = Console(color_system="truecolor", theme=get_nord_theme())
