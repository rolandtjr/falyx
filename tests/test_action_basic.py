import pytest

from falyx.action import Action, ChainedAction, FallbackAction, LiteralInputAction
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
        == "Action(name='test_action', action=async_callable, args=(), kwargs={}, retry=False)"
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
