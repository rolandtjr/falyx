from __future__ import annotations

from typing import Any

import pytest
from rich.tree import Tree

import falyx.action.selection_action as selection_action_module
from falyx.action.action_types import SelectionReturnType
from falyx.action.selection_action import SelectionAction
from falyx.hook_manager import HookType
from falyx.selection import SelectionOption, SelectionOptionMap
from falyx.signals import CancelSignal


class DummyPromptSession:
    pass


class CaptureConsole:
    def __init__(self) -> None:
        self.printed: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.printed.append((args, kwargs))


class FakeSharedContext:
    def __init__(self, value: Any) -> None:
        self.value = value

    def last_result(self) -> Any:
        return self.value


class SizedButUnsupportedSelections:
    def __len__(self) -> int:
        return 0


def make_action(selections: Any | None = None, **overrides: Any) -> SelectionAction:
    defaults: dict[str, Any] = {
        "name": "ChooseThing",
        "selections": (
            selections if selections is not None else ["alpha", "beta", "gamma"]
        ),
        "prompt_session": DummyPromptSession(),
    }
    defaults.update(overrides)
    return SelectionAction(**defaults)


def make_option_map_action(**overrides: Any) -> SelectionAction:
    return make_action(
        {
            "0": SelectionOption("Development", "dev"),
            "1": SelectionOption("Production", "prod"),
            "2": SelectionOption("Staging", "stage"),
        },
        **overrides,
    )


def register_lifecycle_hooks(action: SelectionAction) -> list[tuple[HookType, Any]]:
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


@pytest.mark.asyncio
async def test_selection_list_never_prompt_by_value():
    action = SelectionAction(
        name="test",
        selections=["a", "b", "c"],
        default_selection="b",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == "b"

    result = await action()
    assert result == "b"


@pytest.mark.asyncio
async def test_selection_list_never_prompt_by_index():
    action = SelectionAction(
        name="test",
        selections=["a", "b", "c"],
        default_selection="2",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == "2"

    result = await action()
    assert result == "c"


@pytest.mark.asyncio
async def test_selection_list_never_prompt_by_value_multi_select():
    action = SelectionAction(
        name="test",
        selections=["a", "b", "c"],
        default_selection=["b", "c"],
        never_prompt=True,
        number_selections=2,
    )
    assert action.never_prompt is True
    assert action.default_selection == ["b", "c"]

    result = await action()
    assert result == ["b", "c"]


@pytest.mark.asyncio
async def test_selection_list_never_prompt_by_index_multi_select():
    action = SelectionAction(
        name="test",
        selections=["a", "b", "c"],
        default_selection=["1", "2"],
        never_prompt=True,
        number_selections=2,
    )
    assert action.never_prompt is True
    assert action.default_selection == ["1", "2"]

    result = await action()
    assert result == ["b", "c"]


@pytest.mark.asyncio
async def test_selection_prompt_dict_never_prompt():
    action = SelectionAction(
        name="test",
        selections={"a": "Alpha", "b": "Beta", "c": "Gamma"},
        default_selection="b",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == "b"

    result = await action()
    assert result == "Beta"


@pytest.mark.asyncio
async def test_selection_prompt_dict_never_prompt_by_value():
    action = SelectionAction(
        name="test",
        selections={"a": "Alpha", "b": "Beta", "c": "Gamma"},
        default_selection="Beta",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == "Beta"

    result = await action()
    assert result == "Beta"


@pytest.mark.asyncio
async def test_selection_prompt_dict_never_prompt_by_key():
    action = SelectionAction(
        name="test",
        selections={"a": "Alpha", "b": "Beta", "c": "Gamma"},
        default_selection="b",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == "b"

    result = await action()
    assert result == "Beta"


@pytest.mark.asyncio
async def test_selection_prompt_map_never_prompt_by_key():
    prompt_map = {
        "a": SelectionOption(description="Alpha", value="Alpha Service"),
        "b": SelectionOption(description="Beta", value="Beta Service"),
        "c": SelectionOption(description="Gamma", value="Gamma Service"),
    }
    action = SelectionAction(
        name="test",
        selections=prompt_map,
        default_selection="c",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == "c"

    result = await action()
    assert result == "Gamma Service"


@pytest.mark.asyncio
async def test_selection_prompt_map_never_prompt_by_description():
    prompt_map = {
        "a": SelectionOption(description="Alpha", value="Alpha Service"),
        "b": SelectionOption(description="Beta", value="Beta Service"),
        "c": SelectionOption(description="Gamma", value="Gamma Service"),
    }
    action = SelectionAction(
        name="test",
        selections=prompt_map,
        default_selection="Alpha",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == "Alpha"

    result = await action()
    assert result == "Alpha Service"


@pytest.mark.asyncio
async def test_selection_prompt_map_never_prompt_by_value():
    prompt_map = {
        "a": SelectionOption(description="Alpha", value="Alpha Service"),
        "b": SelectionOption(description="Beta", value="Beta Service"),
        "c": SelectionOption(description="Gamma", value="Gamma Service"),
    }
    action = SelectionAction(
        name="test",
        selections=prompt_map,
        default_selection="Beta Service",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == "Beta Service"

    result = await action()
    assert result == "Beta Service"


@pytest.mark.asyncio
async def test_selection_prompt_dict_never_prompt_by_value_multi_select():
    action = SelectionAction(
        name="test",
        selections={"a": "Alpha", "b": "Beta", "c": "Gamma"},
        default_selection=["Beta", "Gamma"],
        number_selections=2,
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == ["Beta", "Gamma"]

    result = await action()
    assert result == ["Beta", "Gamma"]


@pytest.mark.asyncio
async def test_selection_prompt_dict_never_prompt_by_key_multi_select():
    action = SelectionAction(
        name="test",
        selections={"a": "Alpha", "b": "Beta", "c": "Gamma"},
        default_selection=["a", "b"],
        number_selections=2,
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == ["a", "b"]

    result = await action()
    assert result == ["Alpha", "Beta"]


@pytest.mark.asyncio
async def test_selection_prompt_map_never_prompt_by_key_multi_select():
    prompt_map = {
        "a": SelectionOption(description="Alpha", value="Alpha Service"),
        "b": SelectionOption(description="Beta", value="Beta Service"),
        "c": SelectionOption(description="Gamma", value="Gamma Service"),
    }
    action = SelectionAction(
        name="test",
        selections=prompt_map,
        default_selection=["b", "c"],
        number_selections=2,
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == ["b", "c"]

    result = await action()
    assert result == ["Beta Service", "Gamma Service"]


@pytest.mark.asyncio
async def test_selection_prompt_map_never_prompt_by_description_multi_select():
    prompt_map = {
        "a": SelectionOption(description="Alpha", value="Alpha Service"),
        "b": SelectionOption(description="Beta", value="Beta Service"),
        "c": SelectionOption(description="Gamma", value="Gamma Service"),
    }
    action = SelectionAction(
        name="test",
        selections=prompt_map,
        default_selection=["Alpha", "Gamma"],
        number_selections=2,
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == ["Alpha", "Gamma"]

    result = await action()
    assert result == ["Alpha Service", "Gamma Service"]


@pytest.mark.asyncio
async def test_selection_prompt_map_never_prompt_by_value_multi_select():
    prompt_map = {
        "a": SelectionOption(description="Alpha", value="Alpha Service"),
        "b": SelectionOption(description="Beta", value="Beta Service"),
        "c": SelectionOption(description="Gamma", value="Gamma Service"),
    }
    action = SelectionAction(
        name="test",
        selections=prompt_map,
        default_selection=["Beta Service", "Alpha Service"],
        number_selections=2,
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == ["Beta Service", "Alpha Service"]

    result = await action()
    assert result == ["Beta Service", "Alpha Service"]


@pytest.mark.asyncio
async def test_selection_prompt_map_never_prompt_by_value_wildcard():
    prompt_map = {
        "a": SelectionOption(description="Alpha", value="Alpha Service"),
        "b": SelectionOption(description="Beta", value="Beta Service"),
        "c": SelectionOption(description="Gamma", value="Gamma Service"),
    }
    action = SelectionAction(
        name="test",
        selections=prompt_map,
        default_selection=["Beta Service", "Alpha Service"],
        number_selections="*",
        never_prompt=True,
    )
    assert action.never_prompt is True
    assert action.default_selection == ["Beta Service", "Alpha Service"]

    result = await action()
    assert result == ["Beta Service", "Alpha Service"]


def test_init_normalizes_list_tuple_set_and_basic_configuration() -> None:
    session = DummyPromptSession()

    tuple_action = SelectionAction(
        name="TupleChoice",
        selections=("red", "blue"),
        title="Colors",
        columns=2,
        prompt_message="[bold]Pick >[/] ",
        default_selection="1",
        number_selections=1,
        separator=";",
        allow_duplicates=True,
        return_type="value",
        prompt_session=session,
        never_prompt=True,
        show_table=False,
    )

    assert tuple_action.selections == ["red", "blue"]
    assert tuple_action.return_type is SelectionReturnType.VALUE
    assert tuple_action.title == "Colors"
    assert tuple_action.columns == 2
    assert tuple_action.default_selection == "1"
    assert tuple_action.separator == ";"
    assert tuple_action.allow_duplicates is True
    assert tuple_action.prompt_session is session
    assert tuple_action.local_never_prompt is True
    assert tuple_action.show_table is False

    set_action = make_action({"red", "blue"})
    assert sorted(set_action.selections) == ["blue", "red"]


def test_init_converts_plain_dict_to_selection_option_map() -> None:
    action = make_action({"dev": "Development", "prod": "Production"})

    assert isinstance(action.selections, SelectionOptionMap)
    assert list(action.selections) == ["0", "1"]
    assert action.selections["0"] == SelectionOption("dev", "Development")
    assert action.selections["1"] == SelectionOption("prod", "Production")


def test_init_preserves_selection_option_map_values() -> None:
    action = make_action(
        {
            "D": SelectionOption("Development", "dev", style="green"),
            "P": SelectionOption("Production", "prod", style="red"),
        }
    )

    assert isinstance(action.selections, SelectionOptionMap)
    assert action.selections["D"].description == "Development"
    assert action.selections["P"].value == "prod"


@pytest.mark.parametrize("number_selections", [1, 2, "*"])
def test_number_selections_accepts_positive_ints_and_star(
    number_selections: int | str,
) -> None:
    action = make_action(number_selections=number_selections)

    assert action.number_selections == number_selections


@pytest.mark.parametrize("number_selections", [0, -1, "many", object()])
def test_number_selections_rejects_invalid_values(number_selections: Any) -> None:
    action = make_action()

    with pytest.raises(ValueError, match="number_selections"):
        action.number_selections = number_selections


@pytest.mark.parametrize(
    ("selections", "error_type", "match"),
    [
        ({1: SelectionOption("One", 1)}, ValueError, "Invalid dictionary format"),
        (123, TypeError, "selections"),
    ],
)
def test_selections_setter_rejects_invalid_inputs(
    selections: Any,
    error_type: type[BaseException],
    match: str,
) -> None:
    with pytest.raises(error_type, match=match):
        make_action(selections)


def test_find_cancel_key_returns_numeric_gap_for_dict_and_next_index_for_list() -> None:
    dict_action = make_action(
        {
            "0": SelectionOption("Zero", 0),
            "2": SelectionOption("Two", 2),
        }
    )
    list_action = make_action(["zero", "one"])

    assert dict_action._find_cancel_key() == "1"
    assert list_action._find_cancel_key() == "2"


def test_cancel_key_setter_rejects_non_string_values() -> None:
    action = make_action()

    with pytest.raises(TypeError, match="Cancel key must be a string"):
        action.cancel_key = 1  # type: ignore[assignment]


def test_cancel_key_setter_rejects_existing_dict_key() -> None:
    action = make_action({"A": SelectionOption("Alpha", "alpha")})

    with pytest.raises(
        ValueError, match="Cancel key cannot be one of the selection keys"
    ):
        action.cancel_key = "A"


@pytest.mark.parametrize("cancel_key", ["x", "3"])
def test_cancel_key_setter_rejects_invalid_list_cancel_key(cancel_key: str) -> None:
    action = make_action(["alpha", "beta"])

    with pytest.raises(ValueError, match="cancel_key must be a digit"):
        action.cancel_key = cancel_key


def test_cancel_formatter_marks_cancel_key_and_formats_regular_items() -> None:
    action = make_action(["alpha", "beta"])
    action.cancel_key = "2"

    assert "Cancel" in action.cancel_formatter(2, "Cancel")
    assert action.cancel_formatter(1, "beta").endswith("beta")


def test_get_infer_target_disables_signature_inference() -> None:
    action = make_action()

    assert action.get_infer_target() == (None, None)


@pytest.mark.parametrize(
    ("return_type", "keys", "expected"),
    [
        (SelectionReturnType.KEY, "0", "0"),
        (SelectionReturnType.KEY, ["0", "2"], ["0", "2"]),
        (SelectionReturnType.VALUE, "1", "prod"),
        (SelectionReturnType.VALUE, ["0", "2"], ["dev", "stage"]),
        (SelectionReturnType.DESCRIPTION, "0", "Development"),
        (
            SelectionReturnType.DESCRIPTION,
            ["0", "2"],
            ["Development", "Staging"],
        ),
        (
            SelectionReturnType.DESCRIPTION_VALUE,
            "1",
            {"Production": "prod"},
        ),
        (
            SelectionReturnType.DESCRIPTION_VALUE,
            ["0", "2"],
            {"Development": "dev", "Staging": "stage"},
        ),
    ],
)
def test_get_result_from_keys_returns_configured_shape(
    return_type: SelectionReturnType,
    keys: str | list[str],
    expected: Any,
) -> None:
    action = make_option_map_action(return_type=return_type)

    assert action._get_result_from_keys(keys) == expected


@pytest.mark.parametrize("keys", ["0", ["0", "1"]])
def test_get_result_from_keys_returns_items_mapping(keys: str | list[str]) -> None:
    action = make_option_map_action(return_type=SelectionReturnType.ITEMS)

    result = action._get_result_from_keys(keys)

    assert isinstance(result, dict)
    assert set(result) == ({keys} if isinstance(keys, str) else set(keys))
    assert all(isinstance(option, SelectionOption) for option in result.values())


def test_get_result_from_keys_requires_dict_selections() -> None:
    action = make_action(["alpha", "beta"])

    with pytest.raises(TypeError, match="Selections must be a dictionary"):
        action._get_result_from_keys("0")


def test_get_result_from_keys_rejects_unsupported_return_type() -> None:
    action = make_option_map_action()
    action.return_type = object()  # Force defensive branch unreachable through __init__.

    with pytest.raises(ValueError, match="Unsupported return type"):
        action._get_result_from_keys("0")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("maybe_result", "expected"),
    [
        ("1", "1"),
        ("prod", "1"),
        ("Production", "1"),
    ],
)
async def test_resolve_single_default_maps_dict_key_value_and_description(
    maybe_result: str,
    expected: str,
) -> None:
    action = make_option_map_action()

    assert await action._resolve_single_default(maybe_result) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("maybe_result", "expected"),
    [
        ("1", "1"),
        ("beta", "1"),
        ("missing", ""),
    ],
)
async def test_resolve_single_default_maps_list_index_or_value(
    maybe_result: str,
    expected: str,
) -> None:
    action = make_action(["alpha", "beta"])

    assert await action._resolve_single_default(maybe_result) == expected


@pytest.mark.asyncio
async def test_resolve_effective_default_uses_first_value_for_single_selection_defaults() -> (
    None
):
    action = make_action(["alpha", "beta"], default_selection=["beta"])

    assert await action._resolve_effective_default() == "1"


@pytest.mark.asyncio
async def test_resolve_effective_default_uses_first_last_result_for_single_selection() -> (
    None
):
    action = make_action(["alpha", "beta"])
    action.shared_context = FakeSharedContext(["beta"])

    assert await action._resolve_effective_default() == "1"


@pytest.mark.asyncio
async def test_resolve_effective_default_joins_multi_selection_defaults() -> None:
    action = make_action(
        ["alpha", "beta", "gamma"],
        default_selection=["alpha", "gamma"],
        number_selections=2,
    )

    assert await action._resolve_effective_default() == "0,2"


@pytest.mark.asyncio
async def test_resolve_effective_default_joins_multi_selection_last_result() -> None:
    action = make_action(["alpha", "beta", "gamma"], number_selections=2)
    action.shared_context = FakeSharedContext(["alpha", "gamma"])

    assert await action._resolve_effective_default() == "0,2"


@pytest.mark.asyncio
async def test_resolve_effective_default_allows_unbounded_multi_selection_last_result() -> (
    None
):
    action = make_action(["alpha", "beta", "gamma"], number_selections="*")
    action.shared_context = FakeSharedContext(["alpha", "beta", "gamma"])

    assert await action._resolve_effective_default() == "0,1,2"


@pytest.mark.asyncio
async def test_resolve_effective_default_rejects_default_length_mismatch() -> None:
    action = make_action(
        ["alpha", "beta", "gamma"],
        default_selection=["alpha"],
        number_selections=2,
    )

    with pytest.raises(ValueError, match="default_selection has a different length"):
        await action._resolve_effective_default()


@pytest.mark.asyncio
async def test_resolve_effective_default_rejects_last_result_length_mismatch() -> None:
    action = make_action(["alpha", "beta", "gamma"], number_selections=2)
    action.shared_context = FakeSharedContext(["alpha"])

    with pytest.raises(ValueError, match="last_result has a different length"):
        await action._resolve_effective_default()


@pytest.mark.asyncio
async def test_resolve_effective_default_warns_when_injected_result_is_unusable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = make_action(
        ["alpha", "beta"],
        inject_last_result=True,
        number_selections=2,
    )
    action.shared_context = FakeSharedContext("missing")

    assert await action._resolve_effective_default() == ""
    assert "Injected last result" in caplog.text


@pytest.mark.asyncio
async def test_run_list_headless_single_selection_uses_default() -> None:
    action = make_action(["alpha", "beta"], never_prompt=True, default_selection="1")

    result = await action()

    assert result == "beta"


@pytest.mark.asyncio
async def test_run_list_headless_multi_selection_uses_default_list() -> None:
    action = make_action(
        ["alpha", "beta", "gamma"],
        never_prompt=True,
        default_selection=["alpha", "gamma"],
        number_selections=2,
    )

    result = await action()

    assert result == ["alpha", "gamma"]


@pytest.mark.asyncio
async def test_run_dict_headless_single_selection_returns_value() -> None:
    action = make_option_map_action(never_prompt=True, default_selection="1")

    result = await action()

    assert result == "prod"


@pytest.mark.asyncio
async def test_run_dict_headless_multi_selection_returns_configured_shape() -> None:
    action = make_option_map_action(
        never_prompt=True,
        default_selection=["0", "2"],
        number_selections=2,
        return_type=SelectionReturnType.DESCRIPTION_VALUE,
    )

    result = await action()

    assert result == {"Development": "dev", "Staging": "stage"}


@pytest.mark.asyncio
async def test_run_list_interactive_uses_prompt_for_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = make_action(["alpha", "beta"], never_prompt=False, show_table=False)

    async def fake_prompt_for_index(*args: Any, **kwargs: Any) -> int:
        assert kwargs["prompt_session"] is action.prompt_session
        assert kwargs["show_table"] is False
        assert kwargs["cancel_key"] == "2"
        return 1

    monkeypatch.setattr(
        selection_action_module, "prompt_for_index", fake_prompt_for_index
    )

    result = await action()

    assert result == "beta"


@pytest.mark.asyncio
async def test_run_dict_interactive_uses_prompt_for_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = make_option_map_action(never_prompt=False, show_table=False)

    async def fake_prompt_for_selection(*args: Any, **kwargs: Any) -> str:
        assert kwargs["prompt_session"] is action.prompt_session
        assert kwargs["show_table"] is False
        assert kwargs["cancel_key"] == "3"
        return "2"

    monkeypatch.setattr(
        selection_action_module,
        "prompt_for_selection",
        fake_prompt_for_selection,
    )

    result = await action()

    assert result == "stage"


@pytest.mark.asyncio
async def test_run_raises_when_never_prompt_has_no_effective_default() -> None:
    action = make_action(["alpha", "beta"], never_prompt=True)

    with pytest.raises(ValueError, match="never_prompt"):
        await action()


@pytest.mark.asyncio
async def test_run_list_cancel_triggers_error_and_teardown_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = make_action(["alpha", "beta"], never_prompt=True, default_selection="0")
    calls = register_lifecycle_hooks(action)

    async def fake_resolve_effective_default() -> str:
        return "4"

    monkeypatch.setattr(
        action, "_resolve_effective_default", fake_resolve_effective_default
    )

    with pytest.raises(IndexError):
        await action()

    assert HookType.BEFORE in hook_types(calls)
    assert HookType.ON_ERROR in hook_types(calls)
    assert HookType.AFTER in hook_types(calls)
    assert HookType.ON_TEARDOWN in hook_types(calls)
    error_contexts = [
        context for hook_type, context in calls if hook_type is HookType.ON_ERROR
    ]
    assert isinstance(error_contexts[0].exception, IndexError)


@pytest.mark.asyncio
async def test_run_dict_cancel_triggers_cancel_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = make_option_map_action(never_prompt=True, default_selection="0")

    async def fake_resolve_effective_default() -> str:
        return "3"

    monkeypatch.setattr(
        action, "_resolve_effective_default", fake_resolve_effective_default
    )

    with pytest.raises(CancelSignal):
        await action()


@pytest.mark.asyncio
async def test_run_unsupported_selection_storage_triggers_error_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = make_action(["alpha"], never_prompt=False)
    action._selections = SizedButUnsupportedSelections()  # type: ignore[assignment]
    calls = register_lifecycle_hooks(action)

    async def fake_resolve_effective_default() -> str:
        return ""

    monkeypatch.setattr(
        action, "_resolve_effective_default", fake_resolve_effective_default
    )

    with pytest.raises(TypeError, match="selections"):
        await action()

    assert HookType.ON_ERROR in hook_types(calls)
    error_contexts = [
        context for hook_type, context in calls if hook_type is HookType.ON_ERROR
    ]
    assert isinstance(error_contexts[0].exception, TypeError)


@pytest.mark.asyncio
async def test_run_success_triggers_success_after_and_teardown_hooks() -> None:
    action = make_action(["alpha", "beta"], never_prompt=True, default_selection="0")
    calls = register_lifecycle_hooks(action)

    result = await action()

    assert result == "alpha"
    assert hook_types(calls).count(HookType.BEFORE) == 1
    assert hook_types(calls).count(HookType.ON_SUCCESS) == 1
    assert hook_types(calls).count(HookType.AFTER) == 1
    assert hook_types(calls).count(HookType.ON_TEARDOWN) == 1
    success_contexts = [
        context for hook_type, context in calls if hook_type is HookType.ON_SUCCESS
    ]
    assert success_contexts[0].result == "alpha"


@pytest.mark.asyncio
async def test_preview_prints_tree_when_no_parent() -> None:
    action = make_option_map_action(default_selection="1", never_prompt=True)
    console = CaptureConsole()
    action.console = console  # type: ignore[assignment]

    await action.preview()

    assert len(console.printed) == 1
    assert "SelectionAction" in str(console.printed[0][0][0].label)


@pytest.mark.asyncio
async def test_preview_adds_to_parent_when_parent_is_provided() -> None:
    action = make_action(["alpha", "beta"], default_selection="0")
    parent = Tree("Root")
    console = CaptureConsole()
    action.console = console  # type: ignore[assignment]

    await action.preview(parent=parent)

    assert console.printed == []
    assert len(parent.children) == 1
    assert "SelectionAction" in str(parent.children[0].label)


def test_str_includes_action_configuration() -> None:
    action = make_action(["alpha", "beta"], return_type=SelectionReturnType.KEY)

    text = str(action)

    assert "SelectionAction" in text
    assert "ChooseThing" in text
    assert "KEY" in text or "key" in text


def test_clone_copies_selection_action_configuration() -> None:
    session = DummyPromptSession()
    action = SelectionAction(
        name="CloneMe",
        selections={"A": SelectionOption("Alpha", "alpha", style="green")},
        title="Letters",
        columns=3,
        prompt_message="Choose letter > ",
        default_selection="A",
        number_selections="*",
        separator=";",
        allow_duplicates=True,
        inject_last_result=True,
        inject_into="choice",
        return_type=SelectionReturnType.DESCRIPTION,
        prompt_session=session,
        never_prompt=True,
        show_table=False,
    )

    clone = action.clone()

    assert clone is not action
    assert clone.name == action.name
    assert clone.title == action.title
    assert clone.columns == action.columns
    assert clone.prompt_message == action.prompt_message
    assert clone.default_selection == action.default_selection
    assert clone.number_selections == action.number_selections
    assert clone.separator == action.separator
    assert clone.allow_duplicates == action.allow_duplicates
    assert clone.inject_last_result is True
    assert clone.inject_into == "choice"
    assert clone.return_type is SelectionReturnType.DESCRIPTION
    assert clone.prompt_session is session
    assert clone.local_never_prompt is True
    assert clone.show_table is False
    assert clone.selections is not action.selections
    assert clone.selections["A"].description == "Alpha"
