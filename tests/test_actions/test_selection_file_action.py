from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
import toml
import yaml
from rich.tree import Tree

import falyx.action.select_file_action as select_file_module
from falyx.action.action_types import FileType
from falyx.action.select_file_action import SelectFileAction
from falyx.hook_manager import HookType
from falyx.selection import SelectionOption
from falyx.signals import CancelSignal


class DummyPromptSession:
    pass


class CaptureConsole:
    def __init__(self) -> None:
        self.printed: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.printed.append((args, kwargs))


def make_action(directory: Path, **overrides: Any) -> SelectFileAction:
    defaults: dict[str, Any] = {
        "name": "ChooseFile",
        "directory": directory,
        "prompt_session": DummyPromptSession(),
    }
    defaults.update(overrides)
    return SelectFileAction(**defaults)


def write_sample_files(directory: Path) -> dict[str, Path]:
    paths = {
        "text": directory / "note.txt",
        "json": directory / "config.json",
        "yaml": directory / "config.yaml",
        "toml": directory / "config.toml",
        "csv": directory / "rows.csv",
        "tsv": directory / "rows.tsv",
        "xml": directory / "doc.xml",
    }
    paths["text"].write_text("hello\n", encoding="UTF-8")
    paths["json"].write_text('{"name": "falyx", "count": 2}', encoding="UTF-8")
    paths["yaml"].write_text("name: falyx\nenabled: true\n", encoding="UTF-8")
    paths["toml"].write_text('name = "falyx"\ncount = 2\n', encoding="UTF-8")
    paths["csv"].write_text("name,count\nfalyx,2\n", encoding="UTF-8")
    paths["tsv"].write_text("name\tcount\nfalyx\t2\n", encoding="UTF-8")
    paths["xml"].write_text("<root><name>falyx</name></root>", encoding="UTF-8")
    return paths


def register_lifecycle_hooks(action: SelectFileAction) -> list[tuple[HookType, Any]]:
    calls: list[tuple[HookType, Any]] = []

    def make_hook(hook_type: HookType):
        def hook(context):
            calls.append((hook_type, context))

        return hook

    for hook_type in HookType:
        action.hooks.register(hook_type, make_hook(hook_type))

    return calls


def hook_types(calls: list[tuple[HookType, Any]]) -> list[HookType]:
    return [hook_type for hook_type, _ in calls]


def test_init_normalizes_configuration_and_string_return_type(tmp_path: Path) -> None:
    session = DummyPromptSession()

    action = SelectFileAction(
        "ChooseConfig",
        tmp_path,
        title="Configs",
        columns=4,
        prompt_message="[bold]Pick >[/] ",
        style="green",
        suffix_filter=".json",
        return_type="json",
        encoding="utf-8",
        number_selections="*",
        separator=";",
        allow_duplicates=True,
        prompt_session=session,
        never_prompt=True,
    )

    assert action.name == "ChooseConfig"
    assert action.directory == tmp_path.resolve()
    assert action.title == "Configs"
    assert action.columns == 4
    assert action.suffix_filter == ".json"
    assert action.return_type == FileType.JSON
    assert action.encoding == "utf-8"
    assert action.number_selections == "*"
    assert action.separator == ";"
    assert action.allow_duplicates is True
    assert action.prompt_session is session
    assert action.local_never_prompt is True
    assert "ChooseConfig" in str(action)
    assert ".json" in str(action)


@pytest.mark.parametrize("number_selections", [1, 2, "*"])
def test_number_selections_accepts_positive_ints_and_star(
    tmp_path: Path,
    number_selections: int | str,
) -> None:
    action = make_action(tmp_path, number_selections=number_selections)

    assert action.number_selections == number_selections


@pytest.mark.parametrize("number_selections", [0, -1, "many", object()])
def test_number_selections_rejects_invalid_values(
    tmp_path: Path,
    number_selections: Any,
) -> None:
    action = make_action(tmp_path)

    with pytest.raises(ValueError, match="number_selections"):
        action.number_selections = number_selections


def test_get_options_uses_numeric_keys_and_selection_options(tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("a", encoding="UTF-8")
    second.write_text("b", encoding="UTF-8")
    action = make_action(tmp_path, style="cyan")

    options = action.get_options([first, second])

    assert list(options) == ["0", "1"]
    assert options["0"] == SelectionOption(
        description="a.txt",
        value=first,
        style="cyan",
    )
    assert options["1"].description == "b.txt"
    assert options["1"].value == second


def test_find_cancel_key_returns_first_numeric_gap_or_next_index(tmp_path: Path) -> None:
    action = make_action(tmp_path)

    assert action._find_cancel_key({"0": object(), "2": object()}) == "1"
    assert action._find_cancel_key({"0": object(), "1": object()}) == "2"
    assert action._find_cancel_key({}) == "0"


def test_get_infer_target_disables_signature_inference(tmp_path: Path) -> None:
    action = make_action(tmp_path)

    assert action.get_infer_target() == (None, None)


@pytest.mark.parametrize(
    ("return_type", "file_key", "expected"),
    [
        (FileType.TEXT, "text", "hello\n"),
        (FileType.PATH, "text", "PATH"),
        (FileType.JSON, "json", {"name": "falyx", "count": 2}),
        (FileType.YAML, "yaml", {"name": "falyx", "enabled": True}),
        (FileType.TOML, "toml", {"name": "falyx", "count": 2}),
        (FileType.CSV, "csv", [["name", "count"], ["falyx", "2"]]),
        (FileType.TSV, "tsv", [["name", "count"], ["falyx", "2"]]),
    ],
)
def test_parse_file_returns_requested_representation(
    tmp_path: Path,
    return_type: FileType,
    file_key: str,
    expected: Any,
) -> None:
    files = write_sample_files(tmp_path)
    action = make_action(tmp_path, return_type=return_type)

    result = action.parse_file(files[file_key])

    if expected == "PATH":
        assert result == files[file_key]
    else:
        assert result == expected


def test_parse_file_returns_xml_root(tmp_path: Path) -> None:
    files = write_sample_files(tmp_path)
    action = make_action(tmp_path, return_type=FileType.XML)

    result = action.parse_file(files["xml"])

    assert isinstance(result, ET.Element)
    assert result.tag == "root"
    assert result.findtext("name") == "falyx"


def test_clone_preserves_configuration_but_returns_distinct_action(
    tmp_path: Path,
) -> None:
    session = DummyPromptSession()
    action = make_action(
        tmp_path,
        title="Pick a data file",
        columns=2,
        prompt_message="Select > ",
        style="magenta",
        suffix_filter=".json",
        return_type=FileType.JSON,
        encoding="utf-8",
        number_selections=2,
        separator="|",
        allow_duplicates=True,
        prompt_session=session,
        never_prompt=True,
    )

    clone = action.clone()

    assert clone is not action
    assert clone.name == action.name
    assert clone.directory == action.directory
    assert clone.title == action.title
    assert clone.columns == action.columns
    assert clone.prompt_message == action.prompt_message
    assert clone.style == action.style
    assert clone.suffix_filter == action.suffix_filter
    assert clone.return_type == action.return_type
    assert clone.encoding == action.encoding
    assert clone.number_selections == action.number_selections
    assert clone.separator == action.separator
    assert clone.allow_duplicates == action.allow_duplicates
    assert clone.prompt_session is session
    assert clone.local_never_prompt is True


@pytest.mark.asyncio
async def test_preview_prints_tree_when_no_parent_is_given(tmp_path: Path) -> None:
    write_sample_files(tmp_path)
    action = make_action(tmp_path, suffix_filter=".json", return_type=FileType.JSON)
    action.console = CaptureConsole()

    await action.preview()

    assert len(action.console.printed) == 1
    printed_tree = action.console.printed[0][0][0]
    assert isinstance(printed_tree, Tree)


@pytest.mark.asyncio
async def test_preview_adds_to_existing_parent_and_limits_file_sample(
    tmp_path: Path,
) -> None:
    for index in range(12):
        (tmp_path / f"config-{index}.json").write_text("{}", encoding="UTF-8")
    (tmp_path / "ignore.txt").write_text("ignored", encoding="UTF-8")
    action = make_action(tmp_path, suffix_filter=".json", return_type=FileType.JSON)
    parent = Tree("root")

    await action.preview(parent=parent)

    assert len(parent.children) == 1
    action_tree = parent.children[0]
    rendered_labels = [str(child.label) for child in action_tree.children]
    assert any("Suffix filter" in label and ".json" in label for label in rendered_labels)
    file_list = next(
        child for child in action_tree.children if str(child.label) == "[dim]Files:[/]"
    )
    assert len(file_list.children) == 11
    assert "... (2 more)" in str(file_list.children[-1].label)


@pytest.mark.asyncio
async def test_preview_reports_directory_scan_errors(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"
    action = make_action(missing_dir)
    parent = Tree("root")

    await action.preview(parent=parent)

    action_tree = parent.children[0]
    assert any(
        "Error scanning directory" in str(child.label) for child in action_tree.children
    )


@pytest.mark.asyncio
async def test_run_raises_for_missing_directory_and_triggers_error_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = make_action(tmp_path / "missing")
    calls = register_lifecycle_hooks(action)
    recorded: list[Any] = []
    monkeypatch.setattr(select_file_module.er, "record", recorded.append)

    with pytest.raises(FileNotFoundError, match="does not exist"):
        await action("arg", flag=True)

    assert hook_types(calls) == [
        HookType.BEFORE,
        HookType.ON_ERROR,
        HookType.AFTER,
        HookType.ON_TEARDOWN,
    ]
    assert recorded
    assert isinstance(recorded[0].exception, FileNotFoundError)
    assert recorded[0].args == ("arg",)
    assert recorded[0].kwargs == {"flag": True}


@pytest.mark.asyncio
async def test_run_raises_when_directory_path_is_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory_path = tmp_path / "not-a-dir.txt"
    directory_path.write_text("not a directory", encoding="UTF-8")
    action = make_action(directory_path)
    calls = register_lifecycle_hooks(action)
    monkeypatch.setattr(select_file_module.er, "record", lambda context: None)

    with pytest.raises(NotADirectoryError, match="is not a directory"):
        await action()

    assert HookType.ON_ERROR in hook_types(calls)


@pytest.mark.asyncio
async def test_run_raises_when_suffix_filter_matches_no_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="UTF-8")
    action = make_action(tmp_path, suffix_filter=".json")
    calls = register_lifecycle_hooks(action)
    monkeypatch.setattr(select_file_module.er, "record", lambda context: None)

    with pytest.raises(FileNotFoundError, match="No files found"):
        await action()

    assert HookType.ON_ERROR in hook_types(calls)


@pytest.mark.asyncio
async def test_run_single_selection_returns_parsed_file_and_passes_prompt_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = tmp_path / "note.txt"
    selected.write_text("selected", encoding="UTF-8")
    (tmp_path / "other.json").write_text("{}", encoding="UTF-8")
    action = make_action(
        tmp_path,
        suffix_filter=".txt",
        return_type=FileType.TEXT,
        number_selections=1,
        separator=";",
        allow_duplicates=True,
    )
    calls = register_lifecycle_hooks(action)
    recorded: list[Any] = []
    prompt_calls: list[dict[str, Any]] = []
    render_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(select_file_module.er, "record", recorded.append)

    def fake_render_selection_dict_table(**kwargs: Any) -> object:
        render_calls.append(kwargs)
        return object()

    async def fake_prompt_for_selection(valid_keys, table, **kwargs: Any) -> str:
        prompt_calls.append({"valid_keys": list(valid_keys), "table": table, **kwargs})
        return "0"

    monkeypatch.setattr(
        select_file_module,
        "render_selection_dict_table",
        fake_render_selection_dict_table,
    )
    monkeypatch.setattr(
        select_file_module,
        "prompt_for_selection",
        fake_prompt_for_selection,
    )

    result = await action()

    assert result == "selected"
    assert hook_types(calls) == [
        HookType.BEFORE,
        HookType.ON_SUCCESS,
        HookType.AFTER,
        HookType.ON_TEARDOWN,
    ]
    assert recorded[0].result == "selected"
    assert render_calls[0]["title"] == action.title
    assert render_calls[0]["columns"] == action.columns
    assert set(render_calls[0]["selections"]) == {"0", "1"}
    assert prompt_calls[0]["valid_keys"] == ["0", "1"]
    assert prompt_calls[0]["prompt_session"] is action.prompt_session
    assert prompt_calls[0]["prompt_message"] == action.prompt_message
    assert prompt_calls[0]["number_selections"] == 1
    assert prompt_calls[0]["separator"] == ";"
    assert prompt_calls[0]["allow_duplicates"] is True
    assert prompt_calls[0]["cancel_key"] == "1"


@pytest.mark.asyncio
async def test_run_multi_selection_returns_results_for_each_selected_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("a", encoding="UTF-8")
    second.write_text("b", encoding="UTF-8")
    action = make_action(tmp_path, return_type=FileType.PATH, number_selections=2)
    monkeypatch.setattr(select_file_module.er, "record", lambda context: None)
    monkeypatch.setattr(
        select_file_module,
        "render_selection_dict_table",
        lambda **kwargs: object(),
    )

    async def fake_prompt_for_selection(*args: Any, **kwargs: Any) -> list[str]:
        return ["0", "1"]

    monkeypatch.setattr(
        select_file_module,
        "prompt_for_selection",
        fake_prompt_for_selection,
    )

    result = await action()

    print(result)

    assert result == [first, second] or result == [second, first]


@pytest.mark.asyncio
async def test_run_cancel_selection_raises_cancel_signal_and_skips_error_hook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="UTF-8")
    action = make_action(tmp_path)
    calls = register_lifecycle_hooks(action)
    recorded: list[Any] = []
    monkeypatch.setattr(select_file_module.er, "record", recorded.append)
    monkeypatch.setattr(
        select_file_module,
        "render_selection_dict_table",
        lambda **kwargs: object(),
    )

    async def fake_prompt_for_selection(*args: Any, **kwargs: Any) -> str:
        return kwargs["cancel_key"]

    monkeypatch.setattr(
        select_file_module,
        "prompt_for_selection",
        fake_prompt_for_selection,
    )

    with pytest.raises(CancelSignal, match="User canceled"):
        await action()

    assert hook_types(calls) == [
        HookType.BEFORE,
        HookType.AFTER,
        HookType.ON_TEARDOWN,
    ]
    assert recorded
    assert recorded[0].exception is None


def assert_parse_file_value_error(
    action: SelectFileAction,
    file: Path,
    *,
    expected_cause_type: (
        type[BaseException] | tuple[type[BaseException], ...] | None
    ) = None,
) -> ValueError:
    with pytest.raises(ValueError) as exc_info:
        action.parse_file(file)

    error = exc_info.value
    assert f"Failed to parse {file.name} as" in str(error)
    assert error.__cause__ is not None
    if expected_cause_type is not None:
        assert isinstance(error.__cause__, expected_cause_type)
    return error


def test_parse_file_wraps_invalid_json_errors(tmp_path: Path) -> None:
    import json

    broken = tmp_path / "broken.json"
    broken.write_text('{"name": ', encoding="UTF-8")
    action = make_action(tmp_path, return_type=FileType.JSON)

    assert_parse_file_value_error(
        action, broken, expected_cause_type=json.JSONDecodeError
    )


def test_parse_file_wraps_invalid_toml_errors(tmp_path: Path) -> None:
    broken = tmp_path / "broken.toml"
    broken.write_text('name = "falyx"\ncount = ', encoding="UTF-8")
    action = make_action(tmp_path, return_type=FileType.TOML)

    assert_parse_file_value_error(
        action, broken, expected_cause_type=toml.TomlDecodeError
    )


def test_parse_file_wraps_invalid_yaml_errors(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("name: [unterminated\n", encoding="UTF-8")
    action = make_action(tmp_path, return_type=FileType.YAML)

    assert_parse_file_value_error(action, broken, expected_cause_type=yaml.YAMLError)


def test_parse_file_wraps_invalid_xml_errors(tmp_path: Path) -> None:
    broken = tmp_path / "broken.xml"
    broken.write_text("<root><name>falyx</root>", encoding="UTF-8")
    action = make_action(tmp_path, return_type=FileType.XML)

    assert_parse_file_value_error(action, broken, expected_cause_type=ET.ParseError)


@pytest.mark.parametrize(
    "return_type",
    [
        FileType.TEXT,
        FileType.JSON,
        FileType.YAML,
        FileType.TOML,
        FileType.CSV,
        FileType.TSV,
        FileType.XML,
    ],
)
def test_parse_file_wraps_missing_file_errors(
    tmp_path: Path, return_type: FileType
) -> None:
    missing = tmp_path / "missing.data"
    action = make_action(tmp_path, return_type=return_type)

    assert_parse_file_value_error(action, missing, expected_cause_type=FileNotFoundError)


@pytest.mark.parametrize("return_type", [FileType.CSV, FileType.TSV])
def test_parse_file_wraps_csv_style_open_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    return_type: FileType,
) -> None:
    data_file = tmp_path / "rows.data"
    data_file.write_text("name,count\nfalyx,2\n", encoding="UTF-8")
    action = make_action(tmp_path, return_type=return_type)

    def fake_open(*args: Any, **kwargs: Any) -> Any:
        raise OSError("cannot open test file")

    monkeypatch.setattr("builtins.open", fake_open)

    error = assert_parse_file_value_error(action, data_file, expected_cause_type=OSError)
    assert "cannot open test file" in str(error)


def test_parse_file_wraps_unsupported_return_type_errors(tmp_path: Path) -> None:
    data_file = tmp_path / "note.txt"
    data_file.write_text("hello", encoding="UTF-8")
    action = make_action(tmp_path, return_type=FileType.TEXT)
    action.return_type = object()  # Force the defensive unsupported-type branch.

    error = assert_parse_file_value_error(
        action, data_file, expected_cause_type=ValueError
    )

    assert "Unsupported return type" in str(error.__cause__)
