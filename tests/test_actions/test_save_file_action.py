from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
import toml
import yaml
from rich.tree import Tree

from falyx.action.action_types import FileType
from falyx.action.save_file_action import SaveFileAction
from falyx.hook_manager import HookType


class CaptureConsole:
    def __init__(self) -> None:
        self.printed: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.printed.append((args, kwargs))


def make_action(file_path: Path | str | None, **overrides: Any) -> SaveFileAction:
    defaults: dict[str, Any] = {
        "name": "SaveOutput",
        "file_path": file_path,
    }
    defaults.update(overrides)
    return SaveFileAction(**defaults)


def register_lifecycle_hooks(action: SaveFileAction) -> list[tuple[HookType, Any]]:
    calls: list[tuple[HookType, Any]] = []

    def make_hook(hook_type: HookType):
        def hook(context: Any) -> None:
            calls.append((hook_type, context))

        return hook

    for hook_type in HookType:
        action.hooks.register(hook_type, make_hook(hook_type))

    return calls


def hook_types(calls: list[tuple[HookType, Any]]) -> list[HookType]:
    return [hook_type for hook_type, _ in calls]


def test_init_normalizes_configuration_and_string_file_type(tmp_path: Path) -> None:
    target = tmp_path / "output.json"

    action = SaveFileAction(
        name="SaveJson",
        file_path=str(target),
        file_type="json",
        mode="a",
        encoding="utf-8",
        data={"name": "falyx"},
        overwrite=False,
        create_dirs=False,
        inject_last_result=True,
        inject_into="payload",
        never_prompt=True,
    )

    assert action.name == "SaveJson"
    assert action.file_path == target
    assert action.file_type == FileType.JSON
    assert action.mode == "a"
    assert action.encoding == "utf-8"
    assert action.data == {"name": "falyx"}
    assert action.overwrite is False
    assert action.create_dirs is False
    assert action.inject_last_result is True
    assert action.inject_into == "payload"
    assert action.local_never_prompt is True
    assert "SaveFileAction" in str(action)
    assert "output.json" in str(action)


def test_file_path_property_coerces_string_path_and_none(tmp_path: Path) -> None:
    action = make_action(None)

    assert action.file_path is None

    target = tmp_path / "later.txt"
    action.file_path = str(target)

    assert action.file_path == target

    action.file_path = target

    assert action.file_path == target


def test_file_path_rejects_unsupported_values(tmp_path: Path) -> None:
    action = make_action(tmp_path / "out.txt")

    with pytest.raises(TypeError, match="file_path must be a string or Path object"):
        action.file_path = 123  # type: ignore[assignment]


def test_get_infer_target_disables_signature_inference(tmp_path: Path) -> None:
    action = make_action(tmp_path / "out.txt")

    assert action.get_infer_target() == (None, None)


def test_dict_to_xml_serializes_nested_dicts_lists_and_scalars(tmp_path: Path) -> None:
    action = make_action(tmp_path / "out.xml", file_type=FileType.XML)
    root = ET.Element("root")

    action._dict_to_xml(
        {
            "name": "falyx",
            "metadata": {"version": "0.2.0"},
            "tags": ["cli", "framework"],
            "commands": [{"name": "run"}, {"name": "help"}],
        },
        root,
    )

    assert root.findtext("name") == "falyx"
    assert root.find("metadata") is not None
    assert root.find("metadata/version") is not None
    assert root.findtext("metadata/version") == "0.2.0"
    assert [element.text for element in root.findall("tags")] == ["cli", "framework"]
    assert [element.findtext("name") for element in root.findall("commands")] == [
        "run",
        "help",
    ]


@pytest.mark.asyncio
async def test_save_file_requires_file_path_before_saving() -> None:
    action = make_action(None, data="hello")

    with pytest.raises(ValueError, match="file_path must be set"):
        await action.save_file("hello")


@pytest.mark.asyncio
async def test_save_file_refuses_to_overwrite_existing_file_when_disabled(
    tmp_path: Path,
) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("original", encoding="UTF-8")
    action = make_action(target, overwrite=False)

    with pytest.raises(FileExistsError, match="File already exists"):
        await action.save_file("replacement")

    assert target.read_text(encoding="UTF-8") == "original"


@pytest.mark.asyncio
async def test_save_file_requires_parent_directory_when_create_dirs_is_disabled(
    tmp_path: Path,
) -> None:
    target = tmp_path / "missing" / "out.txt"
    action = make_action(target, create_dirs=False)

    with pytest.raises(FileNotFoundError, match="Directory does not exist"):
        await action.save_file("hello")


@pytest.mark.asyncio
async def test_save_file_creates_missing_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "out.txt"
    action = make_action(target, file_type=FileType.TEXT, create_dirs=True)

    await action.save_file("hello")

    assert target.read_text(encoding="UTF-8") == "hello"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_type", "filename", "data"),
    [
        (FileType.TEXT, "note.txt", "hello"),
        (FileType.JSON, "data.json", {"name": "falyx", "count": 2}),
        (FileType.YAML, "data.yaml", {"name": "falyx", "enabled": True}),
        (FileType.TOML, "data.toml", {"name": "falyx", "count": 2}),
        (FileType.CSV, "rows.csv", [["name", "count"], ["falyx", "2"]]),
        (FileType.TSV, "rows.tsv", [["name", "count"], ["falyx", "2"]]),
        (
            FileType.XML,
            "data.xml",
            {
                "name": "falyx",
                "metadata": {"version": "0.2.0"},
                "tags": ["cli", "framework"],
            },
        ),
    ],
)
async def test_save_file_writes_supported_file_types(
    tmp_path: Path,
    file_type: FileType,
    filename: str,
    data: Any,
) -> None:
    target = tmp_path / filename
    action = make_action(target, file_type=file_type)

    await action.save_file(data)

    if file_type == FileType.TEXT:
        assert target.read_text(encoding="UTF-8") == data
    elif file_type == FileType.JSON:
        assert json.loads(target.read_text(encoding="UTF-8")) == data
    elif file_type == FileType.YAML:
        assert yaml.safe_load(target.read_text(encoding="UTF-8")) == data
    elif file_type == FileType.TOML:
        assert toml.loads(target.read_text(encoding="UTF-8")) == data
    elif file_type == FileType.CSV:
        with target.open(newline="", encoding="UTF-8") as file:
            assert list(csv.reader(file)) == data
    elif file_type == FileType.TSV:
        with target.open(newline="", encoding="UTF-8") as file:
            assert list(csv.reader(file, delimiter="\t")) == data
    elif file_type == FileType.XML:
        root = ET.parse(target).getroot()
        assert root.tag == "root"
        assert root.findtext("name") == "falyx"
        assert root.findtext("metadata/version") == "0.2.0"
        assert [element.text for element in root.findall("tags")] == [
            "cli",
            "framework",
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("file_type", [FileType.CSV, FileType.TSV])
@pytest.mark.parametrize(
    "data",
    [
        {"name": "falyx"},
        ["name", "count"],
        [["name", "count"], "not-a-row"],
    ],
)
async def test_save_file_requires_list_of_lists_for_delimited_formats(
    tmp_path: Path,
    file_type: FileType,
    data: Any,
) -> None:
    target = tmp_path / "rows.data"
    action = make_action(target, file_type=file_type)

    with pytest.raises(ValueError, match="requires a list of lists"):
        await action.save_file(data)


@pytest.mark.asyncio
async def test_save_file_requires_dict_for_xml(tmp_path: Path) -> None:
    target = tmp_path / "data.xml"
    action = make_action(target, file_type=FileType.XML)

    with pytest.raises(
        ValueError, match="XML file type requires data to be a dictionary"
    ):
        await action.save_file(["not", "a", "dict"])


@pytest.mark.asyncio
async def test_save_file_raises_for_unsupported_internal_file_type(
    tmp_path: Path,
) -> None:
    target = tmp_path / "data.out"
    action = make_action(target, file_type=FileType.TEXT)
    action._file_type = object()  # Force the defensive unsupported-type branch.

    with pytest.raises(ValueError, match="Unsupported file type"):
        await action.save_file("hello")


@pytest.mark.asyncio
async def test_save_file_reraises_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "out.txt"
    action = make_action(target, file_type=FileType.TEXT)

    def fake_write_text(self: Path, data: str, *, encoding: str | None = None) -> int:
        raise OSError("disk is unavailable")

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    with pytest.raises(OSError, match="disk is unavailable"):
        await action.save_file("hello")


@pytest.mark.asyncio
async def test_run_saves_configured_data_and_triggers_success_lifecycle(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.txt"
    action = make_action(target, file_type=FileType.TEXT, data="hello")
    calls = register_lifecycle_hooks(action)

    result = await action("positional", ignored="kwarg")

    assert result == str(target)
    assert target.read_text(encoding="UTF-8") == "hello"
    assert hook_types(calls) == [
        HookType.BEFORE,
        HookType.ON_SUCCESS,
        HookType.AFTER,
        HookType.ON_TEARDOWN,
    ]
    assert calls[0][1].args == ("positional",)
    assert calls[0][1].kwargs == {"ignored": "kwarg"}
    assert calls[0][1].action is action


@pytest.mark.asyncio
async def test_run_uses_data_from_kwargs_when_no_static_data_is_configured(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.txt"
    action = make_action(target, file_type=FileType.TEXT, data=None)

    result = await action(data="from kwargs")

    assert result == str(target)
    assert target.read_text(encoding="UTF-8") == "from kwargs"


@pytest.mark.asyncio
async def test_run_triggers_error_lifecycle_and_reraises(tmp_path: Path) -> None:
    action = make_action(None, data="hello")
    calls = register_lifecycle_hooks(action)

    with pytest.raises(ValueError, match="file_path must be set"):
        await action()

    assert hook_types(calls) == [
        HookType.BEFORE,
        HookType.ON_ERROR,
        HookType.AFTER,
        HookType.ON_TEARDOWN,
    ]
    assert isinstance(calls[1][1].exception, ValueError)


@pytest.mark.asyncio
async def test_preview_prints_tree_for_existing_file_when_overwrite_enabled(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.txt"
    target.write_text("existing", encoding="UTF-8")
    action = make_action(target, file_type=FileType.TEXT, overwrite=True)
    action.console = CaptureConsole()

    await action.preview()

    assert len(action.console.printed) == 1
    printed_tree = action.console.printed[0][0][0]
    assert isinstance(printed_tree, Tree)


@pytest.mark.asyncio
async def test_preview_prints_tree_for_existing_file_when_overwrite_disabled(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.txt"
    target.write_text("existing", encoding="UTF-8")
    action = make_action(target, file_type=FileType.TEXT, overwrite=False)
    action.console = CaptureConsole()

    await action.preview()

    assert len(action.console.printed) == 1
    printed_tree = action.console.printed[0][0][0]
    assert isinstance(printed_tree, Tree)


@pytest.mark.asyncio
async def test_preview_adds_to_existing_parent_without_printing(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    action = make_action(target, file_type=FileType.JSON)
    action.console = CaptureConsole()
    parent = Tree("root")

    await action.preview(parent=parent)

    assert action.console.printed == []
    assert len(parent.children) == 1


def test_clone_preserves_configuration_but_returns_distinct_action(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.json"
    action = make_action(
        target,
        file_type=FileType.JSON,
        mode="a",
        encoding="utf-8",
        data={"name": "falyx"},
        overwrite=False,
        create_dirs=False,
        inject_last_result=True,
        inject_into="payload",
        never_prompt=True,
    )

    clone = action.clone()

    assert clone is not action
    assert clone.name == action.name
    assert clone.file_path == action.file_path
    assert clone.file_type == action.file_type
    assert clone.mode == action.mode
    assert clone.encoding == action.encoding
    assert clone.data == action.data
    assert clone.overwrite is action.overwrite
    assert clone.create_dirs is action.create_dirs
    assert clone.inject_last_result is action.inject_last_result
    assert clone.inject_into == action.inject_into
    assert clone.local_never_prompt is True
