# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""tagged_table.py"""
from collections import defaultdict

from rich import box
from rich.table import Table

from falyx.command import Command
from falyx.falyx import Falyx


def build_tagged_table(flx: Falyx) -> Table:
    """Custom table builder that groups commands by tags."""
    table = Table(title=flx.title, show_header=False, box=box.SIMPLE)  # type: ignore[arg-type]

    # Group commands by first tag
    grouped: dict[str, list[Command]] = defaultdict(list)
    for cmd in flx.commands.values():
        first_tag = cmd.tags[0] if cmd.tags else "Other"
        grouped[first_tag.capitalize()].append(cmd)

    # Add grouped commands to table
    for group_name, commands in grouped.items():
        table.add_row(f"[bold underline]{group_name} Commands[/]")
        for cmd in commands:
            table.add_row(f"[{cmd.key}] [{cmd.style}]{cmd.description}")
        table.add_row("")

    # Add bottom row
    for row in flx.get_bottom_row():
        table.add_row(row)

    return table
