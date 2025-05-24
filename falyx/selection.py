# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""selection.py"""
from dataclasses import dataclass
from typing import Any, Callable, KeysView, Sequence

from prompt_toolkit import PromptSession
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from falyx.themes import OneColors
from falyx.utils import CaseInsensitiveDict, chunks
from falyx.validators import int_range_validator, key_validator


@dataclass
class SelectionOption:
    """Represents a single selection option with a description and a value."""

    description: str
    value: Any
    style: str = OneColors.WHITE

    def __post_init__(self):
        if not isinstance(self.description, str):
            raise TypeError("SelectionOption description must be a string.")

    def render(self, key: str) -> str:
        """Render the selection option for display."""
        key = escape(f"[{key}]")
        return f"[{OneColors.WHITE}]{key}[/] [{self.style}]{self.description}[/]"


class SelectionOptionMap(CaseInsensitiveDict):
    """
    Manages selection options including validation and reserved key protection.
    """

    RESERVED_KEYS: set[str] = set()

    def __init__(
        self,
        options: dict[str, SelectionOption] | None = None,
        allow_reserved: bool = False,
    ):
        super().__init__()
        self.allow_reserved = allow_reserved
        if options:
            self.update(options)

    def _add_reserved(self, key: str, option: SelectionOption) -> None:
        """Add a reserved key, bypassing validation."""
        norm_key = key.upper()
        super().__setitem__(norm_key, option)

    def __setitem__(self, key: str, option: SelectionOption) -> None:
        if not isinstance(option, SelectionOption):
            raise TypeError(f"Value for key '{key}' must be a SelectionOption.")
        norm_key = key.upper()
        if norm_key in self.RESERVED_KEYS and not self.allow_reserved:
            raise ValueError(
                f"Key '{key}' is reserved and cannot be used in SelectionOptionMap."
            )
        super().__setitem__(norm_key, option)

    def __delitem__(self, key: str) -> None:
        if key.upper() in self.RESERVED_KEYS and not self.allow_reserved:
            raise ValueError(f"Cannot delete reserved option '{key}'.")
        super().__delitem__(key)

    def update(self, other=None, **kwargs):
        """Update the selection options with another dictionary."""
        if other:
            for key, option in other.items():
                if not isinstance(option, SelectionOption):
                    raise TypeError(f"Value for key '{key}' must be a SelectionOption.")
                self[key] = option
        for key, option in kwargs.items():
            if not isinstance(option, SelectionOption):
                raise TypeError(f"Value for key '{key}' must be a SelectionOption.")
            self[key] = option

    def items(self, include_reserved: bool = True):
        for k, v in super().items():
            if not include_reserved and k in self.RESERVED_KEYS:
                continue
            yield k, v


def render_table_base(
    title: str,
    *,
    caption: str = "",
    columns: int = 4,
    box_style: box.Box = box.SIMPLE,
    show_lines: bool = False,
    show_header: bool = False,
    show_footer: bool = False,
    style: str = "",
    header_style: str = "",
    footer_style: str = "",
    title_style: str = "",
    caption_style: str = "",
    highlight: bool = True,
    column_names: Sequence[str] | None = None,
) -> Table:
    table = Table(
        title=title,
        caption=caption,
        box=box_style,
        show_lines=show_lines,
        show_header=show_header,
        show_footer=show_footer,
        style=style,
        header_style=header_style,
        footer_style=footer_style,
        title_style=title_style,
        caption_style=caption_style,
        highlight=highlight,
    )
    if column_names:
        for column_name in column_names:
            table.add_column(column_name)
    else:
        for _ in range(columns):
            table.add_column()
    return table


def render_selection_grid(
    title: str,
    selections: Sequence[str],
    *,
    columns: int = 4,
    caption: str = "",
    box_style: box.Box = box.SIMPLE,
    show_lines: bool = False,
    show_header: bool = False,
    show_footer: bool = False,
    style: str = "",
    header_style: str = "",
    footer_style: str = "",
    title_style: str = "",
    caption_style: str = "",
    highlight: bool = False,
) -> Table:
    """Create a selection table with the given parameters."""
    table = render_table_base(
        title=title,
        caption=caption,
        columns=columns,
        box_style=box_style,
        show_lines=show_lines,
        show_header=show_header,
        show_footer=show_footer,
        style=style,
        header_style=header_style,
        footer_style=footer_style,
        title_style=title_style,
        caption_style=caption_style,
        highlight=highlight,
    )

    for chunk in chunks(selections, columns):
        table.add_row(*chunk)

    return table


def render_selection_indexed_table(
    title: str,
    selections: Sequence[str],
    *,
    columns: int = 4,
    caption: str = "",
    box_style: box.Box = box.SIMPLE,
    show_lines: bool = False,
    show_header: bool = False,
    show_footer: bool = False,
    style: str = "",
    header_style: str = "",
    footer_style: str = "",
    title_style: str = "",
    caption_style: str = "",
    highlight: bool = False,
    formatter: Callable[[int, str], str] | None = None,
) -> Table:
    """Create a selection table with the given parameters."""
    table = render_table_base(
        title=title,
        caption=caption,
        columns=columns,
        box_style=box_style,
        show_lines=show_lines,
        show_header=show_header,
        show_footer=show_footer,
        style=style,
        header_style=header_style,
        footer_style=footer_style,
        title_style=title_style,
        caption_style=caption_style,
        highlight=highlight,
    )

    for indexes, chunk in zip(
        chunks(range(len(selections)), columns), chunks(selections, columns)
    ):
        row = [
            formatter(index, selection) if formatter else f"[{index}] {selection}"
            for index, selection in zip(indexes, chunk)
        ]
        table.add_row(*row)

    return table


def render_selection_dict_table(
    title: str,
    selections: dict[str, SelectionOption],
    *,
    columns: int = 2,
    caption: str = "",
    box_style: box.Box = box.SIMPLE,
    show_lines: bool = False,
    show_header: bool = False,
    show_footer: bool = False,
    style: str = "",
    header_style: str = "",
    footer_style: str = "",
    title_style: str = "",
    caption_style: str = "",
    highlight: bool = False,
) -> Table:
    """Create a selection table with the given parameters."""
    table = render_table_base(
        title=title,
        caption=caption,
        columns=columns,
        box_style=box_style,
        show_lines=show_lines,
        show_header=show_header,
        show_footer=show_footer,
        style=style,
        header_style=header_style,
        footer_style=footer_style,
        title_style=title_style,
        caption_style=caption_style,
        highlight=highlight,
    )

    for chunk in chunks(selections.items(), columns):
        row = []
        for key, option in chunk:
            row.append(
                f"[{OneColors.WHITE}][{key.upper()}] "
                f"[{option.style}]{option.description}[/]"
            )
        table.add_row(*row)

    return table


async def prompt_for_index(
    max_index: int,
    table: Table,
    *,
    min_index: int = 0,
    default_selection: str = "",
    console: Console | None = None,
    prompt_session: PromptSession | None = None,
    prompt_message: str = "Select an option > ",
    show_table: bool = True,
) -> int:
    prompt_session = prompt_session or PromptSession()
    console = console or Console(color_system="auto")

    if show_table:
        console.print(table, justify="center")

    selection = await prompt_session.prompt_async(
        message=prompt_message,
        validator=int_range_validator(min_index, max_index),
        default=default_selection,
    )
    return int(selection)


async def prompt_for_selection(
    keys: Sequence[str] | KeysView[str],
    table: Table,
    *,
    default_selection: str = "",
    console: Console | None = None,
    prompt_session: PromptSession | None = None,
    prompt_message: str = "Select an option > ",
    show_table: bool = True,
) -> str:
    """Prompt the user to select a key from a set of options. Return the selected key."""
    prompt_session = prompt_session or PromptSession()
    console = console or Console(color_system="auto")

    if show_table:
        console.print(table, justify="center")

    selected = await prompt_session.prompt_async(
        message=prompt_message,
        validator=key_validator(keys),
        default=default_selection,
    )

    return selected


async def select_value_from_list(
    title: str,
    selections: Sequence[str],
    *,
    console: Console | None = None,
    prompt_session: PromptSession | None = None,
    prompt_message: str = "Select an option > ",
    default_selection: str = "",
    columns: int = 4,
    caption: str = "",
    box_style: box.Box = box.SIMPLE,
    show_lines: bool = False,
    show_header: bool = False,
    show_footer: bool = False,
    style: str = "",
    header_style: str = "",
    footer_style: str = "",
    title_style: str = "",
    caption_style: str = "",
    highlight: bool = False,
):
    """Prompt for a selection. Return the selected item."""
    table = render_selection_indexed_table(
        title=title,
        selections=selections,
        columns=columns,
        caption=caption,
        box_style=box_style,
        show_lines=show_lines,
        show_header=show_header,
        show_footer=show_footer,
        style=style,
        header_style=header_style,
        footer_style=footer_style,
        title_style=title_style,
        caption_style=caption_style,
        highlight=highlight,
    )
    prompt_session = prompt_session or PromptSession()
    console = console or Console(color_system="auto")

    selection_index = await prompt_for_index(
        len(selections) - 1,
        table,
        default_selection=default_selection,
        console=console,
        prompt_session=prompt_session,
        prompt_message=prompt_message,
    )

    return selections[selection_index]


async def select_key_from_dict(
    selections: dict[str, SelectionOption],
    table: Table,
    *,
    console: Console | None = None,
    prompt_session: PromptSession | None = None,
    prompt_message: str = "Select an option > ",
    default_selection: str = "",
) -> Any:
    """Prompt for a key from a dict, returns the key."""
    prompt_session = prompt_session or PromptSession()
    console = console or Console(color_system="auto")

    console.print(table, justify="center")

    return await prompt_for_selection(
        selections.keys(),
        table,
        default_selection=default_selection,
        console=console,
        prompt_session=prompt_session,
        prompt_message=prompt_message,
    )


async def select_value_from_dict(
    selections: dict[str, SelectionOption],
    table: Table,
    *,
    console: Console | None = None,
    prompt_session: PromptSession | None = None,
    prompt_message: str = "Select an option > ",
    default_selection: str = "",
) -> Any:
    """Prompt for a key from a dict, but return the value."""
    prompt_session = prompt_session or PromptSession()
    console = console or Console(color_system="auto")

    console.print(table, justify="center")

    selection_key = await prompt_for_selection(
        selections.keys(),
        table,
        default_selection=default_selection,
        console=console,
        prompt_session=prompt_session,
        prompt_message=prompt_message,
    )

    return selections[selection_key].value


async def get_selection_from_dict_menu(
    title: str,
    selections: dict[str, SelectionOption],
    *,
    console: Console | None = None,
    prompt_session: PromptSession | None = None,
    prompt_message: str = "Select an option > ",
    default_selection: str = "",
):
    """Prompt for a key from a dict, but return the value."""
    table = render_selection_dict_table(
        title,
        selections,
    )

    return await select_value_from_dict(
        selections=selections,
        table=table,
        console=console,
        prompt_session=prompt_session,
        prompt_message=prompt_message,
        default_selection=default_selection,
    )
