import pytest

from falyx.action import SelectionAction
from falyx.selection import SelectionOption


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
