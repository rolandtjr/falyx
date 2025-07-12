# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""load_file_action.py"""
import csv
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import toml
import yaml
from rich.tree import Tree

from falyx.action.action_types import FileType
from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.themes import OneColors


class LoadFileAction(BaseAction):
    """LoadFileAction allows loading and parsing files of various types."""

    def __init__(
        self,
        name: str,
        file_path: str | Path | None = None,
        file_type: FileType | str = FileType.TEXT,
        inject_last_result: bool = False,
        inject_into: str = "file_path",
    ):
        super().__init__(
            name=name, inject_last_result=inject_last_result, inject_into=inject_into
        )
        self._file_path = self._coerce_file_path(file_path)
        self._file_type = self._coerce_file_type(file_type)

    @property
    def file_path(self) -> Path | None:
        """Get the file path as a Path object."""
        return self._file_path

    @file_path.setter
    def file_path(self, value: str | Path):
        """Set the file path, converting to Path if necessary."""
        self._file_path = self._coerce_file_path(value)

    def _coerce_file_path(self, file_path: str | Path | None) -> Path | None:
        """Coerce the file path to a Path object."""
        if isinstance(file_path, Path):
            return file_path
        elif isinstance(file_path, str):
            return Path(file_path)
        elif file_path is None:
            return None
        else:
            raise TypeError("file_path must be a string or Path object")

    @property
    def file_type(self) -> FileType:
        """Get the file type."""
        return self._file_type

    @file_type.setter
    def file_type(self, value: FileType | str):
        """Set the file type, converting to FileType if necessary."""
        self._file_type = self._coerce_file_type(value)

    def _coerce_file_type(self, file_type: FileType | str) -> FileType:
        """Coerce the file type to a FileType enum."""
        if isinstance(file_type, FileType):
            return file_type
        elif isinstance(file_type, str):
            return FileType(file_type)
        else:
            raise TypeError("file_type must be a FileType enum or string")

    def get_infer_target(self) -> tuple[None, None]:
        return None, None

    async def load_file(self) -> Any:
        """Load and parse the file based on its type."""
        if self.file_path is None:
            raise ValueError("file_path must be set before loading a file")
        elif not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        elif not self.file_path.is_file():
            raise ValueError(f"Path is not a regular file: {self.file_path}")
        value: Any = None
        try:
            if self.file_type == FileType.TEXT:
                value = self.file_path.read_text(encoding="UTF-8")
            elif self.file_type == FileType.PATH:
                value = self.file_path
            elif self.file_type == FileType.JSON:
                value = json.loads(self.file_path.read_text(encoding="UTF-8"))
            elif self.file_type == FileType.TOML:
                value = toml.loads(self.file_path.read_text(encoding="UTF-8"))
            elif self.file_type == FileType.YAML:
                value = yaml.safe_load(self.file_path.read_text(encoding="UTF-8"))
            elif self.file_type == FileType.CSV:
                with open(self.file_path, newline="", encoding="UTF-8") as csvfile:
                    reader = csv.reader(csvfile)
                    value = list(reader)
            elif self.file_type == FileType.TSV:
                with open(self.file_path, newline="", encoding="UTF-8") as tsvfile:
                    reader = csv.reader(tsvfile, delimiter="\t")
                    value = list(reader)
            elif self.file_type == FileType.XML:
                tree = ET.parse(self.file_path, parser=ET.XMLParser(encoding="UTF-8"))
                root = tree.getroot()
                value = ET.tostring(root, encoding="unicode")
            else:
                raise ValueError(f"Unsupported return type: {self.file_type}")

        except Exception as error:
            logger.error("Failed to parse %s: %s", self.file_path.name, error)
        return value

    async def _run(self, *args, **kwargs) -> Any:
        context = ExecutionContext(name=self.name, args=args, kwargs=kwargs, action=self)
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            if "file_path" in kwargs:
                self.file_path = kwargs["file_path"]
            elif self.inject_last_result and self.last_result:
                self.file_path = self.last_result

            result = await self.load_file()
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
        label = f"[{OneColors.GREEN}]📄 LoadFileAction[/] '{self.name}'"
        tree = parent.add(label) if parent else Tree(label)

        tree.add(f"[dim]Path:[/] {self.file_path}")
        tree.add(f"[dim]Type:[/] {self.file_type.name if self.file_type else 'None'}")
        if self.file_path is None:
            tree.add(f"[{OneColors.DARK_RED_b}]❌ File path is not set[/]")
        elif not self.file_path.exists():
            tree.add(f"[{OneColors.DARK_RED_b}]❌ File does not exist[/]")
        elif not self.file_path.is_file():
            tree.add(f"[{OneColors.LIGHT_YELLOW_b}]⚠️ Not a regular file[/]")
        else:
            try:
                stat = self.file_path.stat()
                tree.add(f"[dim]Size:[/] {stat.st_size:,} bytes")
                tree.add(
                    f"[dim]Modified:[/] {datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M:%S}"
                )
                tree.add(
                    f"[dim]Created:[/] {datetime.fromtimestamp(stat.st_ctime):%Y-%m-%d %H:%M:%S}"
                )
                if self.file_type == FileType.TEXT:
                    preview_lines = self.file_path.read_text(
                        encoding="UTF-8"
                    ).splitlines()[:10]
                    content_tree = tree.add("[dim]Preview (first 10 lines):[/]")
                    for line in preview_lines:
                        content_tree.add(f"[dim]{line}[/]")
                elif self.file_type in {FileType.JSON, FileType.YAML, FileType.TOML}:
                    raw = self.load_file()
                    if raw is not None:
                        preview_str = (
                            json.dumps(raw, indent=2)
                            if isinstance(raw, dict)
                            else str(raw)
                        )
                        preview_lines = preview_str.splitlines()[:10]
                        content_tree = tree.add("[dim]Parsed preview:[/]")
                        for line in preview_lines:
                            content_tree.add(f"[dim]{line}[/]")
            except Exception as e:
                tree.add(f"[{OneColors.DARK_RED_b}]❌ Error reading file:[/] {e}")

        if not parent:
            self.console.print(tree)

    def __str__(self) -> str:
        return f"LoadFileAction(file_path={self.file_path}, file_type={self.file_type})"
