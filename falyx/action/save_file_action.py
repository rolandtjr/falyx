# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""save_file_action.py"""
import csv
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

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


class SaveFileAction(BaseAction):
    """
    SaveFileAction saves data to a file in the specified format (e.g., TEXT, JSON, YAML).
    Supports overwrite control and integrates with chaining workflows via inject_last_result.

    Supported types: TEXT, JSON, YAML, TOML, CSV, TSV, XML

    If the file exists and overwrite is False, the action will raise a FileExistsError.
    """

    def __init__(
        self,
        name: str,
        file_path: str,
        file_type: FileType | str = FileType.TEXT,
        mode: Literal["w", "a"] = "w",
        inject_last_result: bool = True,
        inject_into: str = "data",
        overwrite: bool = True,
    ):
        """
        SaveFileAction allows saving data to a file.

        Args:
            name (str): Name of the action.
            file_path (str | Path): Path to the file where data will be saved.
            file_type (FileType | str): Format to write to (e.g. TEXT, JSON, YAML).
            inject_last_result (bool): Whether to inject result from previous action.
            inject_into (str): Kwarg name to inject the last result as.
            overwrite (bool): Whether to overwrite the file if it exists.
        """
        super().__init__(
            name=name, inject_last_result=inject_last_result, inject_into=inject_into
        )
        self._file_path = self._coerce_file_path(file_path)
        self._file_type = self._coerce_file_type(file_type)
        self.overwrite = overwrite
        self.mode = mode

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

    def _dict_to_xml(self, data: dict, root: ET.Element) -> None:
        """Convert a dictionary to XML format."""
        for key, value in data.items():
            if isinstance(value, dict):
                sub_element = ET.SubElement(root, key)
                self._dict_to_xml(value, sub_element)
            elif isinstance(value, list):
                for item in value:
                    item_element = ET.SubElement(root, key)
                    if isinstance(item, dict):
                        self._dict_to_xml(item, item_element)
                    else:
                        item_element.text = str(item)
            else:
                element = ET.SubElement(root, key)
                element.text = str(value)

    async def save_file(self, data: Any) -> None:
        """Save data to the specified file in the desired format."""
        if self.file_path is None:
            raise ValueError("file_path must be set before saving a file")
        elif self.file_path.exists() and not self.overwrite:
            raise FileExistsError(f"File already exists: {self.file_path}")

        try:
            if self.file_type == FileType.TEXT:
                self.file_path.write_text(data, encoding="UTF-8")
            elif self.file_type == FileType.JSON:
                self.file_path.write_text(json.dumps(data, indent=4), encoding="UTF-8")
            elif self.file_type == FileType.TOML:
                self.file_path.write_text(toml.dumps(data), encoding="UTF-8")
            elif self.file_type == FileType.YAML:
                self.file_path.write_text(yaml.dump(data), encoding="UTF-8")
            elif self.file_type == FileType.CSV:
                if not isinstance(data, list) or not all(
                    isinstance(row, list) for row in data
                ):
                    raise ValueError(
                        f"{self.file_type.name} file type requires a list of lists"
                    )
                with open(
                    self.file_path, mode=self.mode, newline="", encoding="UTF-8"
                ) as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerows(data)
            elif self.file_type == FileType.TSV:
                if not isinstance(data, list) or not all(
                    isinstance(row, list) for row in data
                ):
                    raise ValueError(
                        f"{self.file_type.name} file type requires a list of lists"
                    )
                with open(
                    self.file_path, mode=self.mode, newline="", encoding="UTF-8"
                ) as tsvfile:
                    writer = csv.writer(tsvfile, delimiter="\t")
                    writer.writerows(data)
            elif self.file_type == FileType.XML:
                if not isinstance(data, dict):
                    raise ValueError("XML file type requires data to be a dictionary")
                root = ET.Element("root")
                self._dict_to_xml(data, root)
                tree = ET.ElementTree(root)
                tree.write(self.file_path, encoding="UTF-8", xml_declaration=True)
            else:
                raise ValueError(f"Unsupported file type: {self.file_type}")

        except Exception as error:
            logger.error("Failed to save %s: %s", self.file_path.name, error)
            raise

    async def _run(self, *args, **kwargs):
        combined_kwargs = self._maybe_inject_last_result(kwargs)
        data = combined_kwargs.get(self.inject_into)

        context = ExecutionContext(
            name=self.name, args=args, kwargs=combined_kwargs, action=self
        )
        context.start_timer()

        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            await self.save_file(data)
            logger.debug("File saved successfully: %s", self.file_path)

            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return str(self.file_path)

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
        label = f"[{OneColors.CYAN}]💾 SaveFileAction[/] '{self.name}'"
        tree = parent.add(label) if parent else Tree(label)

        tree.add(f"[dim]Path:[/] {self.file_path}")
        tree.add(f"[dim]Type:[/] {self.file_type.name}")
        tree.add(f"[dim]Overwrite:[/] {self.overwrite}")

        if self.file_path and self.file_path.exists():
            if self.overwrite:
                tree.add(f"[{OneColors.LIGHT_YELLOW}]⚠️ File will be overwritten[/]")
            else:
                tree.add(
                    f"[{OneColors.DARK_RED}]❌ File exists and overwrite is disabled[/]"
                )
            stat = self.file_path.stat()
            tree.add(f"[dim]Size:[/] {stat.st_size:,} bytes")
            tree.add(
                f"[dim]Modified:[/] {datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M:%S}"
            )
            tree.add(
                f"[dim]Created:[/] {datetime.fromtimestamp(stat.st_ctime):%Y-%m-%d %H:%M:%S}"
            )

        if not parent:
            self.console.print(tree)

    def __str__(self) -> str:
        return f"SaveFileAction(file_path={self.file_path}, file_type={self.file_type})"
