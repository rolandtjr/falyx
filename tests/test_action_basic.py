import pytest

from falyx.action import (
    Action,
    ActionGroup,
    ChainedAction,
    FallbackAction,
    LiteralInputAction,
)
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er

asyncio_default_fixture_loop_scope = "function"


# --- Helpers ---
async def capturing_hook(context: ExecutionContext):
    context.extra["hook_triggered"] = True


# --- Fixtures ---
@pytest.fixture(autouse=True)
def clean_registry():
    er.clear()
    yield
    er.clear()


@pytest.mark.asyncio
async def test_action_callable():
    """Test if Action can be created with a callable."""
    action = Action("test_action", lambda: "Hello, World!")
    result = await action()
    assert result == "Hello, World!"


@pytest.mark.asyncio
async def test_action_async_callable():
    """Test if Action can be created with an async callable."""

    async def async_callable():
        return "Hello, World!"

    action = Action("test_action", async_callable)
    result = await action()
    assert result == "Hello, World!"
    assert (
        str(action)
        == "Action(name='test_action', action=async_callable, args=(), kwargs={}, retry=False, rollback=False)"
    )
    assert (
        repr(action)
        == "Action(name='test_action', action=async_callable, args=(), kwargs={}, retry=False, rollback=False)"
    )


@pytest.mark.asyncio
async def test_chained_action():
    """Test if ChainedAction can be created and used."""
    action1 = Action("one", lambda: 1)
    action2 = Action("two", lambda: 2)
    chain = ChainedAction(
        name="Simple Chain",
        actions=[action1, action2],
        return_list=True,
    )

    print(chain)
    result = await chain()
    assert result == [1, 2]
    assert (
        str(chain)
        == "ChainedAction(name=Simple Chain, actions=['one', 'two'], args=(), kwargs={}, auto_inject=False, return_list=True)"
    )


@pytest.mark.asyncio
async def test_action_group():
    """Test if ActionGroup can be created and used."""
    action1 = Action("one", lambda: 1)
    action2 = Action("two", lambda: 2)
    group = ActionGroup(
        name="Simple Group",
        actions=[action1, action2],
    )

    print(group)
    result = await group()
    assert result == [("one", 1), ("two", 2)]
    assert (
        str(group)
        == "ActionGroup(name=Simple Group, actions=['one', 'two'], args=(), kwargs={}, inject_last_result=False, inject_into=last_result)"
    )


@pytest.mark.asyncio
async def test_action_non_callable():
    """Test if Action raises an error when created with a non-callable."""
    with pytest.raises(TypeError):
        Action("test_action", 42)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "return_list, expected",
    [
        (True, [1, 2, 3]),
        (False, 3),
    ],
)
async def test_chained_action_return_modes(return_list, expected):
    chain = ChainedAction(
        name="Simple Chain",
        actions=[
            Action(name="one", action=lambda: 1),
            Action(name="two", action=lambda: 2),
            Action(name="three", action=lambda: 3),
        ],
        return_list=return_list,
    )

    result = await chain()
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "return_list, auto_inject, expected",
    [
        (True, True, [1, 2, 3]),
        (True, False, [1, 2, 3]),
        (False, True, 3),
        (False, False, 3),
    ],
)
async def test_chained_action_literals(return_list, auto_inject, expected):
    chain = ChainedAction(
        name="Literal Chain",
        actions=[1, 2, 3],
        return_list=return_list,
        auto_inject=auto_inject,
    )

    result = await chain()
    assert result == expected


@pytest.mark.asyncio
async def test_literal_input_action():
    """Test if LiteralInputAction can be created and used."""
    action = LiteralInputAction("Hello, World!")
    result = await action()
    assert result == "Hello, World!"
    assert action.value == "Hello, World!"
    assert str(action) == "LiteralInputAction(value='Hello, World!')"


@pytest.mark.asyncio
async def test_fallback_action():
    """Test if FallbackAction can be created and used."""
    action = FallbackAction("Fallback value")
    chain = ChainedAction(
        name="Fallback Chain",
        actions=[
            Action(name="one", action=lambda: None),
            action,
        ],
    )
    result = await chain()
    assert result == "Fallback value"
    assert str(action) == "FallbackAction(fallback='Fallback value')"


@pytest.mark.asyncio
async def test_remove_action_from_chain():
    """Test if an action can be removed from a chain."""
    action1 = Action(name="one", action=lambda: 1)
    action2 = Action(name="two", action=lambda: 2)
    chain = ChainedAction(
        name="Simple Chain",
        actions=[action1, action2],
    )

    assert len(chain.actions) == 2

    # Remove the first action
    chain.remove_action(action1.name)

    assert len(chain.actions) == 1
    assert chain.actions[0] == action2


@pytest.mark.asyncio
async def test_has_action_in_chain():
    """Test if an action can be checked for presence in a chain."""
    action1 = Action(name="one", action=lambda: 1)
    action2 = Action(name="two", action=lambda: 2)
    chain = ChainedAction(
        name="Simple Chain",
        actions=[action1, action2],
    )

    assert chain.has_action(action1.name) is True
    assert chain.has_action(action2.name) is True

    # Remove the first action
    chain.remove_action(action1.name)

    assert chain.has_action(action1.name) is False
    assert chain.has_action(action2.name) is True


@pytest.mark.asyncio
async def test_get_action_from_chain():
    """Test if an action can be retrieved from a chain."""
    action1 = Action(name="one", action=lambda: 1)
    action2 = Action(name="two", action=lambda: 2)
    chain = ChainedAction(
        name="Simple Chain",
        actions=[action1, action2],
    )

    assert chain.get_action(action1.name) == action1
    assert chain.get_action(action2.name) == action2

    # Remove the first action
    chain.remove_action(action1.name)

    assert chain.get_action(action1.name) is None
    assert chain.get_action(action2.name) == action2
