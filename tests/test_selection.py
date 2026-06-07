from __future__ import annotations

from typing import Any

import pytest
from rich import box
from rich.table import Table

import falyx.selection as selection_module
from falyx.selection import (
    SelectionOption,
    SelectionOptionMap,
    get_selection_from_dict_menu,
    prompt_for_index,
    prompt_for_selection,
    render_selection_dict_table,
    render_selection_grid,
    render_selection_indexed_table,
    render_table_base,
    select_key_from_dict,
    select_value_from_dict,
    select_value_from_list,
)
from falyx.themes import OneColors


class CaptureConsole:
    def __init__(self) -> None:
        self.printed: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.printed.append((args, kwargs))


class FakePromptSession:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.message: Any = "original-message"
        self.validator: Any = "original-validator"
        self.placeholder: Any = "original-placeholder"

    async def prompt_async(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append((args, kwargs))
        self.message = kwargs.get("message")
        self.validator = kwargs.get("validator")
        self.placeholder = kwargs.get("placeholder")
        if not self.responses:
            raise AssertionError("No fake prompt response configured")
        return self.responses.pop(0)


@pytest.fixture
def sample_options() -> dict[str, SelectionOption]:
    return {
        "dev": SelectionOption("Development", "dev-value", style="green"),
        "prod": SelectionOption("Production", "prod-value", style="red"),
        "stage": SelectionOption("Staging", "stage-value", style="yellow"),
    }


def test_selection_option_rejects_non_string_description() -> None:
    with pytest.raises(TypeError, match="description must be a string"):
        SelectionOption(123, "value")  # type: ignore[arg-type]


def test_selection_option_render_escapes_key_and_applies_style() -> None:
    option = SelectionOption("Deploy [prod]", "prod", style="red")

    rendered = option.render("a[b]")

    assert "a" in rendered
    assert "Deploy [prod]" in rendered
    assert f"[{OneColors.WHITE}]" in rendered
    assert "[red]" in rendered


def test_selection_option_copy_returns_independent_equivalent_option() -> None:
    option = SelectionOption("Development", {"env": "dev"}, style="green")

    copied = option.copy()

    assert copied == option
    assert copied is not option


def test_selection_option_map_initializes_from_options_case_insensitively(
    sample_options: dict[str, SelectionOption],
) -> None:
    mapping = SelectionOptionMap({"dev": sample_options["dev"]})

    assert mapping["DEV"] is sample_options["dev"]
    assert mapping["dev"] is sample_options["dev"]
    assert list(mapping.items()) == [("DEV", sample_options["dev"])]


def test_selection_option_map_rejects_non_selection_option_values() -> None:
    mapping = SelectionOptionMap()

    with pytest.raises(TypeError, match="must be a SelectionOption"):
        mapping["bad"] = "not an option"  # type: ignore[assignment]

    with pytest.raises(TypeError, match="must be a SelectionOption"):
        mapping.update({"bad": "not an option"})

    with pytest.raises(TypeError, match="must be a SelectionOption"):
        mapping.update(bad="not an option")


def test_selection_option_map_update_accepts_kwargs_and_copy_is_deep_for_options(
    sample_options: dict[str, SelectionOption],
) -> None:
    mapping = SelectionOptionMap()
    mapping.update(dev=sample_options["dev"])
    mapping.update({"prod": sample_options["prod"]})

    copied = mapping.copy()

    assert copied.allow_reserved is mapping.allow_reserved
    assert copied["DEV"] == mapping["dev"]
    assert copied["DEV"] is not mapping["dev"]
    assert copied["PROD"].description == "Production"


def test_selection_option_map_reserved_key_protection_and_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SelectionOptionMap, "RESERVED_KEYS", {"QUIT"})
    mapping = SelectionOptionMap()
    reserved_option = SelectionOption("Quit", None)

    with pytest.raises(ValueError, match="reserved"):
        mapping["quit"] = reserved_option

    mapping._add_reserved("quit", reserved_option)
    assert mapping["QUIT"] is reserved_option

    with pytest.raises(ValueError, match="Cannot delete reserved option"):
        del mapping["quit"]

    assert list(mapping.items(include_reserved=False)) == []


def test_selection_option_map_allows_reserved_key_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SelectionOptionMap, "RESERVED_KEYS", {"QUIT"})
    mapping = SelectionOptionMap(allow_reserved=True)
    option = SelectionOption("Quit", None)

    mapping["quit"] = option
    assert mapping["QUIT"] is option

    del mapping["quit"]
    assert "QUIT" not in mapping


def test_render_table_base_uses_explicit_column_names_and_styles() -> None:
    table = render_table_base(
        "Environments",
        caption="Choose carefully",
        column_names=["Name", "Description"],
        box_style=box.ROUNDED,
        show_lines=True,
        show_header=True,
        show_footer=True,
        style="blue",
        header_style="bold",
        footer_style="dim",
        title_style="green",
        caption_style="yellow",
        highlight=False,
    )

    assert isinstance(table, Table)
    assert table.title == "Environments"
    assert table.caption == "Choose carefully"
    assert len(table.columns) == 2
    assert table.columns[0].header == "Name"
    assert table.columns[1].header == "Description"
    assert table.show_header is True
    assert table.show_footer is True
    assert table.highlight is False


def test_render_table_base_creates_blank_columns_when_no_names_are_given() -> None:
    table = render_table_base("Choices", columns=3)

    assert len(table.columns) == 3


def test_render_selection_grid_chunks_rows() -> None:
    table = render_selection_grid("Choices", ["alpha", "beta", "gamma"], columns=2)

    assert table.title == "Choices"
    assert len(table.columns) == 2
    assert len(table.rows) == 2


def test_render_selection_indexed_table_uses_default_and_custom_formatters() -> None:
    default_table = render_selection_indexed_table(
        "Indexed", ["alpha", "beta", "gamma"], columns=2
    )
    formatted_table = render_selection_indexed_table(
        "Formatted",
        ["alpha", "beta"],
        columns=2,
        formatter=lambda index, value: f"{index}:{value.upper()}",
    )

    assert len(default_table.rows) == 2
    assert len(formatted_table.rows) == 1


def test_render_selection_dict_table_renders_option_rows(
    sample_options: dict[str, SelectionOption],
) -> None:
    table = render_selection_dict_table(
        "Environments",
        sample_options,
        columns=2,
        caption="Pick one",
        highlight=True,
    )

    assert table.title == "Environments"
    assert table.caption == "Pick one"
    assert len(table.columns) == 2
    assert len(table.rows) == 2
    assert table.highlight is True


@pytest.mark.asyncio
async def test_prompt_for_index_returns_single_index_and_restores_prompt_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = CaptureConsole()
    monkeypatch.setattr(selection_module, "console", fake_console)
    session = FakePromptSession(" 2 ")
    table = render_table_base("Choices")

    result = await prompt_for_index(
        5,
        table,
        default_selection="1",
        prompt_session=session,  # type: ignore[arg-type]
        prompt_message="[bold]Pick >[/] ",
        show_table=True,
        number_selections=1,
        cancel_key="9",
    )

    assert result == 2
    assert len(fake_console.printed) == 1
    _, kwargs = session.calls[0]
    assert kwargs["default"] == "1"
    assert kwargs["placeholder"] == "Enter selection"
    assert kwargs["validator"].__class__.__name__ == "MultiIndexValidator"
    assert session.message == "original-message"
    assert session.validator == "original-validator"
    assert session.placeholder == "original-placeholder"


@pytest.mark.asyncio
async def test_prompt_for_index_returns_cancel_key_as_int() -> None:
    session = FakePromptSession(" 7 ")
    table = render_table_base("Choices")

    result = await prompt_for_index(
        7,
        table,
        prompt_session=session,  # type: ignore[arg-type]
        show_table=False,
        cancel_key="7",
    )

    assert result == 7


@pytest.mark.asyncio
async def test_prompt_for_index_returns_multiple_indexes_with_custom_separator() -> None:
    session = FakePromptSession("0 ; 2 ; 4")
    table = render_table_base("Choices")

    result = await prompt_for_index(
        5,
        table,
        prompt_session=session,  # type: ignore[arg-type]
        show_table=False,
        number_selections=3,
        separator=";",
        allow_duplicates=True,
    )

    assert result == [0, 2, 4]
    _, kwargs = session.calls[0]
    assert kwargs["placeholder"] == "Enter 3 selections separated by ';'"
    assert kwargs["validator"].__class__.__name__ == "MultiIndexValidator"


@pytest.mark.asyncio
async def test_prompt_for_selection_returns_single_key_and_prints_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = CaptureConsole()
    monkeypatch.setattr(selection_module, "console", fake_console)
    session = FakePromptSession(" DEV ")
    table = render_table_base("Choices")

    result = await prompt_for_selection(
        ["DEV", "PROD"],
        table,
        default_selection="PROD",
        prompt_session=session,  # type: ignore[arg-type]
        prompt_message="Select > ",
        show_table=True,
        number_selections=1,
        cancel_key="Q",
    )

    assert result == "DEV"
    assert len(fake_console.printed) == 1
    _, kwargs = session.calls[0]
    assert kwargs["default"] == "PROD"
    assert kwargs["placeholder"] == "Enter selection"
    assert kwargs["validator"].__class__.__name__ == "MultiKeyValidator"


@pytest.mark.asyncio
async def test_prompt_for_selection_returns_cancel_key() -> None:
    session = FakePromptSession(" q ")
    table = render_table_base("Choices")

    result = await prompt_for_selection(
        ["dev", "prod", "q"],
        table,
        prompt_session=session,  # type: ignore[arg-type]
        show_table=False,
        cancel_key="q",
    )

    assert result == "q"


@pytest.mark.asyncio
async def test_prompt_for_selection_returns_multiple_keys_with_custom_separator() -> None:
    session = FakePromptSession("dev | prod | stage")
    table = render_table_base("Choices")

    result = await prompt_for_selection(
        ["dev", "prod", "stage"],
        table,
        prompt_session=session,  # type: ignore[arg-type]
        show_table=False,
        number_selections="*",
        separator="|",
        allow_duplicates=True,
    )

    assert result == ["dev", "prod", "stage"]
    _, kwargs = session.calls[0]
    assert kwargs["placeholder"] == "Enter selections separated by '|'"


@pytest.mark.asyncio
async def test_select_value_from_list_returns_single_and_multiple_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt_calls: list[dict[str, Any]] = []

    async def fake_prompt_for_index(max_index: int, table: Table, **kwargs: Any) -> Any:
        prompt_calls.append({"max_index": max_index, "table": table, **kwargs})
        return [0, 2] if kwargs["number_selections"] != 1 else 1

    monkeypatch.setattr(selection_module, "prompt_for_index", fake_prompt_for_index)

    single = await select_value_from_list(
        "Languages",
        ["python", "rust", "go"],
        default_selection="1",
        number_selections=1,
    )
    multiple = await select_value_from_list(
        "Languages",
        ["python", "rust", "go"],
        default_selection="0,2",
        number_selections=2,
    )

    assert single == "rust"
    assert multiple == ["python", "go"]
    assert prompt_calls[0]["max_index"] == 2
    assert prompt_calls[0]["default_selection"] == "1"
    assert prompt_calls[1]["number_selections"] == 2


@pytest.mark.asyncio
async def test_select_key_from_dict_delegates_to_prompt_for_selection(
    monkeypatch: pytest.MonkeyPatch,
    sample_options: dict[str, SelectionOption],
) -> None:
    fake_console = CaptureConsole()
    monkeypatch.setattr(selection_module, "console", fake_console)
    calls: list[dict[str, Any]] = []

    async def fake_prompt_for_selection(keys: Any, table: Table, **kwargs: Any) -> str:
        calls.append({"keys": list(keys), "table": table, **kwargs})
        return "prod"

    monkeypatch.setattr(
        selection_module, "prompt_for_selection", fake_prompt_for_selection
    )
    table = render_table_base("Environments")

    result = await select_key_from_dict(
        sample_options,
        table,
        default_selection="dev",
        number_selections=1,
        cancel_key="q",
    )

    assert result == "prod"
    assert len(fake_console.printed) == 1
    assert calls[0]["keys"] == ["dev", "prod", "stage"]
    assert calls[0]["default_selection"] == "dev"
    assert calls[0]["cancel_key"] == "q"


@pytest.mark.asyncio
async def test_select_value_from_dict_returns_single_and_multiple_values(
    monkeypatch: pytest.MonkeyPatch,
    sample_options: dict[str, SelectionOption],
) -> None:
    fake_console = CaptureConsole()
    monkeypatch.setattr(selection_module, "console", fake_console)
    responses: list[Any] = ["prod", ["dev", "stage"]]

    async def fake_prompt_for_selection(keys: Any, table: Table, **kwargs: Any) -> Any:
        return responses.pop(0)

    monkeypatch.setattr(
        selection_module, "prompt_for_selection", fake_prompt_for_selection
    )
    table = render_table_base("Environments")

    single = await select_value_from_dict(sample_options, table)
    multiple = await select_value_from_dict(
        sample_options,
        table,
        number_selections=2,
        separator=",",
    )

    assert single == "prod-value"
    assert multiple == ["dev-value", "stage-value"]
    assert len(fake_console.printed) == 2


@pytest.mark.asyncio
async def test_get_selection_from_dict_menu_builds_table_and_returns_selected_value(
    monkeypatch: pytest.MonkeyPatch,
    sample_options: dict[str, SelectionOption],
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_select_value_from_dict(
        *, selections: dict[str, SelectionOption], table: Table, **kwargs: Any
    ) -> str:
        calls.append({"selections": selections, "table": table, **kwargs})
        return "prod-value"

    monkeypatch.setattr(
        selection_module, "select_value_from_dict", fake_select_value_from_dict
    )

    result = await get_selection_from_dict_menu(
        "Environments",
        sample_options,
        default_selection="prod",
        number_selections=1,
        cancel_key="q",
    )

    assert result == "prod-value"
    assert calls[0]["selections"] is sample_options
    assert calls[0]["table"].title == "Environments"
    assert calls[0]["default_selection"] == "prod"
    assert calls[0]["cancel_key"] == "q"
