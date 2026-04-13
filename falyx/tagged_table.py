# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Generates a Rich table view of Falyx commands grouped by their tags.

This module defines a utility function for rendering a custom CLI command
table that organizes commands into groups based on their first tag. It is
used to visually separate commands in interactive menus for better clarity
and discoverability.

Functions:
- build_tagged_table(flx): Returns a `rich.Table` of commands grouped by tag.
"""
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
    for command in flx.commands.values():
        first_tag = command.tags[0] if command.tags else "Other"
        grouped[first_tag.capitalize()].append(command)

    # Add grouped commands to table
    for group_name, commands in grouped.items():
        table.add_row(f"[bold underline]{group_name} Commands[/]")
        for command in commands:
            table.add_row(f"[{command.key}] [{command.style}]{command.description}")
        table.add_row("")

    # Add bottom row
    for row in flx._get_bottom_row():
        table.add_row(row)

    return table
