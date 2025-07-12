# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""select_file_action.py"""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import toml
import yaml
from prompt_toolkit import PromptSession
from rich.tree import Tree

from falyx.action.action_types import FileType
from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.selection import (
    SelectionOption,
    prompt_for_selection,
    render_selection_dict_table,
)
from falyx.signals import CancelSignal
from falyx.themes import OneColors


class SelectFileAction(BaseAction):
    """
    SelectFileAction allows users to select a file from a directory and return:
    - file content (as text, JSON, CSV, etc.)
    - or the file path itself.

    Supported formats: text, json, yaml, toml, csv, tsv, xml.

    Useful for:
    - dynamically loading config files
    - interacting with user-selected data
    - chaining file contents into workflows

    Args:
        name (str): Name of the action.
        directory (Path | str): Where to search for files.
        title (str): Title of the selection menu.
        columns (int): Number of columns in the selection menu.
        prompt_message (str): Message to display when prompting for selection.
        style (str): Style for the selection options.
        suffix_filter (str | None): Restrict to certain file types.
        return_type (FileType): What to return (path, content, parsed).
        prompt_session (PromptSession | None): Prompt session for user input.
    """

    def __init__(
        self,
        name: str,
        directory: Path | str = ".",
        *,
        title: str = "Select a file",
        columns: int = 3,
        prompt_message: str = "Choose > ",
        style: str = OneColors.WHITE,
        suffix_filter: str | None = None,
        return_type: FileType | str = FileType.PATH,
        number_selections: int | str = 1,
        separator: str = ",",
        allow_duplicates: bool = False,
        prompt_session: PromptSession | None = None,
    ):
        super().__init__(name)
        self.directory = Path(directory).resolve()
        self.title = title
        self.columns = columns
        self.prompt_message = prompt_message
        self.suffix_filter = suffix_filter
        self.style = style
        self.number_selections = number_selections
        self.separator = separator
        self.allow_duplicates = allow_duplicates
        self.prompt_session = prompt_session or PromptSession()
        self.return_type = self._coerce_return_type(return_type)

    @property
    def number_selections(self) -> int | str:
        return self._number_selections

    @number_selections.setter
    def number_selections(self, value: int | str):
        if isinstance(value, int) and value > 0:
            self._number_selections: int | str = value
        elif isinstance(value, str):
            if value not in ("*"):
                raise ValueError("number_selections string must be one of '*'")
            self._number_selections = value
        else:
            raise ValueError("number_selections must be a positive integer or one of '*'")

    def _coerce_return_type(self, return_type: FileType | str) -> FileType:
        if isinstance(return_type, FileType):
            return return_type
        elif isinstance(return_type, str):
            return FileType(return_type)
        else:
            raise TypeError("return_type must be a FileType enum or string")

    def get_options(self, files: list[Path]) -> dict[str, SelectionOption]:
        value: Any
        options = {}
        for index, file in enumerate(files):
            try:
                if self.return_type == FileType.TEXT:
                    value = file.read_text(encoding="UTF-8")
                elif self.return_type == FileType.PATH:
                    value = file
                elif self.return_type == FileType.JSON:
                    value = json.loads(file.read_text(encoding="UTF-8"))
                elif self.return_type == FileType.TOML:
                    value = toml.loads(file.read_text(encoding="UTF-8"))
                elif self.return_type == FileType.YAML:
                    value = yaml.safe_load(file.read_text(encoding="UTF-8"))
                elif self.return_type == FileType.CSV:
                    with open(file, newline="", encoding="UTF-8") as csvfile:
                        reader = csv.reader(csvfile)
                        value = list(reader)
                elif self.return_type == FileType.TSV:
                    with open(file, newline="", encoding="UTF-8") as tsvfile:
                        reader = csv.reader(tsvfile, delimiter="\t")
                        value = list(reader)
                elif self.return_type == FileType.XML:
                    tree = ET.parse(file, parser=ET.XMLParser(encoding="UTF-8"))
                    root = tree.getroot()
                    value = ET.tostring(root, encoding="unicode")
                else:
                    raise ValueError(f"Unsupported return type: {self.return_type}")

                options[str(index)] = SelectionOption(
                    description=file.name, value=value, style=self.style
                )
            except Exception as error:
                logger.error("Failed to parse %s: %s", file.name, error)
        return options

    def _find_cancel_key(self, options) -> str:
        """Return first numeric value not already used in the selection dict."""
        for index in range(len(options)):
            if str(index) not in options:
                return str(index)
        return str(len(options))

    def get_infer_target(self) -> tuple[None, None]:
        return None, None

    async def _run(self, *args, **kwargs) -> Any:
        context = ExecutionContext(name=self.name, args=args, kwargs=kwargs, action=self)
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            if not self.directory.exists():
                raise FileNotFoundError(f"Directory {self.directory} does not exist.")
            elif not self.directory.is_dir():
                raise NotADirectoryError(f"{self.directory} is not a directory.")

            files = [
                file
                for file in self.directory.iterdir()
                if file.is_file()
                and (self.suffix_filter is None or file.suffix == self.suffix_filter)
            ]
            if not files:
                raise FileNotFoundError("No files found in directory.")

            options = self.get_options(files)

            cancel_key = self._find_cancel_key(options)
            cancel_option = {
                cancel_key: SelectionOption(
                    description="Cancel", value=CancelSignal(), style=OneColors.DARK_RED
                )
            }

            table = render_selection_dict_table(
                title=self.title, selections=options | cancel_option, columns=self.columns
            )

            keys = await prompt_for_selection(
                (options | cancel_option).keys(),
                table,
                prompt_session=self.prompt_session,
                prompt_message=self.prompt_message,
                number_selections=self.number_selections,
                separator=self.separator,
                allow_duplicates=self.allow_duplicates,
                cancel_key=cancel_key,
            )

            if isinstance(keys, str):
                if keys == cancel_key:
                    raise CancelSignal("User canceled the selection.")
                result = options[keys].value
            elif isinstance(keys, list):
                result = [options[key].value for key in keys]

            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return result
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def preview(self, parent: Tree | None = None):
        label = f"[{OneColors.GREEN}]📁 SelectFilesAction[/] '{self.name}'"
        tree = parent.add(label) if parent else Tree(label)

        tree.add(f"[dim]Directory:[/] {str(self.directory)}")
        tree.add(f"[dim]Suffix filter:[/] {self.suffix_filter or 'None'}")
        tree.add(f"[dim]Return type:[/] {self.return_type}")
        tree.add(f"[dim]Prompt:[/] {self.prompt_message}")
        tree.add(f"[dim]Columns:[/] {self.columns}")
        try:
            files = list(self.directory.iterdir())
            if self.suffix_filter:
                files = [file for file in files if file.suffix == self.suffix_filter]
            sample = files[:10]
            file_list = tree.add("[dim]Files:[/]")
            for file in sample:
                file_list.add(f"[dim]{file.name}[/]")
            if len(files) > 10:
                file_list.add(f"[dim]... ({len(files) - 10} more)[/]")
        except Exception as error:
            tree.add(f"[{OneColors.DARK_RED_b}]⚠️ Error scanning directory: {error}[/]")

        if not parent:
            self.console.print(tree)

    def __str__(self) -> str:
        return (
            f"SelectFilesAction(name={self.name!r}, dir={str(self.directory)!r}, "
            f"suffix_filter={self.suffix_filter!r}, return_type={self.return_type})"
        )
